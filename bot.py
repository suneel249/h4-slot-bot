"""
H4 Slot Alert Bot
=================
Runs a small Flask web server on PORT (default 8000) that handles the
Telegram user-account authentication flow entirely through the browser.

Auth flow
---------
1. GET  /          → phone-number form
2. POST /auth/phone → sends the Telegram OTP, shows OTP form
3. POST /auth/otp   → completes sign-in, saves session, starts the bot

Once the session file exists the bot starts immediately on the next
deploy without showing the auth UI at all.
"""

import asyncio
import os
import threading
from datetime import datetime

from flask import Flask, request, redirect, url_for
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetHistoryRequest

# ── CONFIG ───────────────────────────────────────────────────────────────────
API_ID       = os.environ.get("API_ID")
API_HASH     = os.environ.get("API_HASH")
YOUR_CHAT_ID = 6350674200          # Telegram user-ID to receive alerts (Suneel)
SESSION_PATH = "/app/session/h4_monitor"
PORT         = int(os.environ.get("PORT", 8000))

# ── CHANNELS TO MONITOR ──────────────────────────────────────────────────────
CHANNELS = [
    "us_visa_stamping_india",
    "h1b_slots",
    "h1bh4chennai",
    "H1BVisaHelp",
]

# ── GLOBALS ──────────────────────────────────────────────────────────────────
client: TelegramClient | None = None
_phone_code_hash: str | None  = None   # returned by Telegram after sending OTP
_phone_number: str | None     = None   # stored between the two POST steps

# ── KEYWORD MATCHING ─────────────────────────────────────────────────────────
def is_relevant(text: str) -> bool:
    """Return True if the message contains H4/slot-related keywords."""
    if not text:
        return False
    t = text.lower()
    has_slot     = any(k in t for k in ["slot", "available", "availability", "opening", "appointment"])
    has_location = any(k in t for k in ["hyderabad", "hyd", "chennai", "mas"])
    has_visa     = any(k in t for k in ["h4", "h1", "visa", "stamping"])
    return (has_slot or has_location) and has_visa

# ── ALERT SENDER ─────────────────────────────────────────────────────────────
async def send_alert(message_text: str, date: datetime, channel_name: str):
    alert = (
        "🚨 *H4 SLOT ALERT* 🚨\n"
        "──────────────────────\n"
        f"📅 *Posted:* {date.strftime('%d %b %Y, %I:%M %p')} IST\n"
        f"📢 *Channel:* @{channel_name}\n\n"
        f"{message_text}\n\n"
        "──────────────────────\n"
        "⚡ via suneel\\_alertBot"
    )
    await client.send_message(YOUR_CHAT_ID, alert, parse_mode="markdown")

# ── EVENT HANDLER ─────────────────────────────────────────────────────────────
async def on_new_message(event):
    text         = event.message.message
    channel_name = event.chat.username or event.chat.title
    if is_relevant(text):
        print(f"[MATCH] {datetime.now()} | @{channel_name} → {text[:80]}...")
        await send_alert(text, event.message.date, channel_name)
    else:
        print(f"[SKIP]  {datetime.now()} | @{channel_name} → {text[:60]}...")

# ── STARTUP HISTORY CHECK ─────────────────────────────────────────────────────
async def startup_check():
    print(f"🔍 Checking last 20 messages from {len(CHANNELS)} channel(s)...")
    for ch in CHANNELS:
        print(f"   → Checking @{ch}...")
        try:
            channel = await client.get_entity(ch)
            history = await client(GetHistoryRequest(
                peer=channel, limit=20, offset_date=None,
                offset_id=0, max_id=0, min_id=0, add_offset=0, hash=0,
            ))
            matched = 0
            for msg in reversed(history.messages):
                if hasattr(msg, "message") and is_relevant(msg.message):
                    await send_alert(msg.message, msg.date, ch)
                    matched += 1
                    await asyncio.sleep(1)
            print(f"   ✅ @{ch} — {matched} relevant message(s) found.")
        except Exception as e:
            print(f"   ❌ Error checking @{ch}: {e}")

# ── BOT RUNNER (called after successful auth) ─────────────────────────────────
async def run_bot():
    global client
    print("🤖 Starting bot monitoring loop...")
    client.add_event_handler(on_new_message, events.NewMessage(chats=CHANNELS))

    channel_list = "\n".join([f"  • @{ch}" for ch in CHANNELS])
    await client.send_message(
        YOUR_CHAT_ID,
        "✅ *H4 Slot Alert Bot is now LIVE!*\n\n"
        f"👁 Monitoring {len(CHANNELS)} channel(s):\n"
        f"{channel_list}\n\n"
        "📍 Locations: Hyderabad & Chennai\n"
        "🎯 Visa type: H4 slots\n\n"
        "I'll notify you the moment a slot is mentioned!",
        parse_mode="markdown",
    )
    await startup_check()
    print("👂 Listening for new messages...")
    await client.run_until_disconnected()

def start_bot_in_background(loop: asyncio.AbstractEventLoop):
    """Schedule run_bot() onto the already-running event loop."""
    asyncio.run_coroutine_threadsafe(run_bot(), loop)

# ── HTML HELPERS ──────────────────────────────────────────────────────────────
_STYLE = """
<style>
  body { font-family: sans-serif; max-width: 480px; margin: 80px auto; padding: 0 16px; }
  h2   { color: #2c3e50; }
  input[type=text], input[type=tel] {
    width: 100%; padding: 10px; font-size: 16px;
    border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box;
  }
  button {
    margin-top: 12px; padding: 10px 24px; font-size: 16px;
    background: #2980b9; color: #fff; border: none;
    border-radius: 6px; cursor: pointer;
  }
  button:hover { background: #1a6fa0; }
  .note { font-size: 13px; color: #666; margin-top: 8px; }
  .ok   { color: green; }
  .err  { color: red; }
</style>
"""

def _page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><title>{title}</title>{_STYLE}</head><body>{body}</body></html>"

# ── FLASK APP ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.get("/")
def index():
    """Show phone-number form, or a 'bot is running' page if already authed."""
    if client and client.is_connected():
        return _page("Bot Running", "<h2 class='ok'>✅ Bot is running</h2><p>The H4 Slot Alert Bot is authenticated and monitoring channels.</p>")
    return _page("Telegram Auth", """
        <h2>🔐 Telegram Authentication</h2>
        <p>Enter your Telegram phone number to authenticate the bot.</p>
        <form method='POST' action='/auth/phone'>
          <input type='tel' name='phone' placeholder='+919876543210' required autofocus>
          <p class='note'>Include country code, e.g. +91 for India.</p>
          <button type='submit'>Send OTP →</button>
        </form>
    """)

@app.post("/auth/phone")
def auth_phone():
    """Receive phone number, ask Telegram to send the OTP."""
    global _phone_number, _phone_code_hash, client

    phone = request.form.get("phone", "").strip()
    if not phone:
        return redirect(url_for("index"))

    loop = asyncio.get_event_loop()

    async def _send_code():
        global client, _phone_code_hash
        os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)
        client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        _phone_code_hash = result.phone_code_hash

    try:
        asyncio.run_coroutine_threadsafe(_send_code(), loop).result(timeout=30)
    except Exception as e:
        return _page("Error", f"<h2 class='err'>❌ Error</h2><p>{e}</p><p><a href='/'>← Try again</a></p>")

    _phone_number = phone
    return _page("Enter OTP", f"""
        <h2>📲 Enter the OTP</h2>
        <p>A code was sent to <strong>{phone}</strong> via Telegram.</p>
        <form method='POST' action='/auth/otp'>
          <input type='text' name='otp' placeholder='12345' maxlength='10' required autofocus>
          <p class='note'>Check your Telegram app for the login code.</p>
          <button type='submit'>Verify →</button>
        </form>
    """)

@app.post("/auth/otp")
def auth_otp():
    """Receive OTP, complete sign-in, then launch the bot."""
    global _phone_number, _phone_code_hash

    otp = request.form.get("otp", "").strip()
    if not otp or not _phone_number or not _phone_code_hash:
        return redirect(url_for("index"))

    loop = asyncio.get_event_loop()

    async def _sign_in():
        await client.sign_in(
            phone=_phone_number,
            code=otp,
            phone_code_hash=_phone_code_hash,
        )

    try:
        asyncio.run_coroutine_threadsafe(_sign_in(), loop).result(timeout=30)
    except Exception as e:
        return _page("Error", f"<h2 class='err'>❌ Sign-in failed</h2><p>{e}</p><p><a href='/'>← Try again</a></p>")

    # Auth succeeded — kick off the monitoring loop
    start_bot_in_background(loop)

    return _page("Success", """
        <h2 class='ok'>✅ Authenticated!</h2>
        <p>Session saved. The bot is now starting up and will monitor channels.</p>
        <p>You can close this tab. Refresh to check bot status.</p>
    """)

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    # Create a single event loop that both asyncio tasks and Flask→asyncio
    # bridge calls will share.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # If a valid session already exists, skip the web auth and go straight
    # to monitoring.
    session_file = SESSION_PATH + ".session"

    async def _start_from_session() -> bool:
        """Try to start the client from an existing session file.

        Returns True if the session is valid and the bot has been started,
        False if the session is corrupted/unregistered (caller should fall
        back to web auth).
        """
        global client

        def _no_stdin_phone():
            """Raise immediately so client.start() never blocks on stdin."""
            raise RuntimeError("Session is invalid — phone input suppressed")

        client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
        try:
            # client.start() validates the session by checking the auth key
            # with Telegram.  If the key is unregistered it raises before
            # trying to call our phone callback; if it IS called it means
            # the session file is simply missing/empty, so we raise ourselves.
            await client.start(phone=_no_stdin_phone)
        except Exception as e:
            print(f"⚠️  Session validation failed ({e}) — deleting corrupted session.")
            await client.disconnect()
            try:
                os.remove(session_file)
            except OSError:
                pass
            return False

        # Session is valid — launch the monitoring loop.
        await run_bot()
        return True  # never actually reached (run_bot blocks), but satisfies type

    # Start the event loop on a background thread so both the session-
    # validation coroutine and the Flask→asyncio bridge can use it.
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()

    if os.path.exists(session_file):
        print("✅ Existing session found — validating...")

        import concurrent.futures

        # Schedule session validation on the now-running loop.
        future = asyncio.run_coroutine_threadsafe(_start_from_session(), loop)

        # Block briefly to detect an immediately-invalid session so we can
        # show the web-auth form before Flask starts accepting requests.
        session_valid = True
        try:
            # 15 s is enough for Telegram to reject a bad auth key; a good
            # session will still be running run_bot() so we'll hit the timeout.
            session_valid = future.result(timeout=15)
        except concurrent.futures.TimeoutError:
            # Still running — session is valid and the bot is starting up.
            session_valid = True
        except Exception as e:
            print(f"⚠️  Unexpected error during session start: {e}")
            session_valid = False

        if not session_valid:
            print("⚠️  Invalid session deleted — open the Railway URL to re-authenticate.")
    else:
        print("⚠️  No session found — open the Railway URL to authenticate.")

    print(f"🌐 Web server listening on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)


if __name__ == "__main__":
    main()

