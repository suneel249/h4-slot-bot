import asyncio
import re
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetHistoryRequest

# ── CONFIG ──────────────────────────────────────────────────────────────────
BOT_TOKEN      = "8655632402:AAGKOJmBsS4JOKICMBdlD09FmvMICMMFzpA"          # Replace with your new token from @BotFather
API_ID         = "31964194"             # Replace after Step 3 belown
API_HASH       = "c1604faf6412fef686bb6590993c8ab1"           # Replace after Step 3 below
YOUR_CHAT_ID   = 6350674200                     # Your Telegram ID (Suneel)
CHANNEL        = "us_visa_stamping_india"       # Public channel to monitor

# ── CHANNELS TO MONITOR ─────────────────────────────────────────────────────
CHANNELS = [
    "us_visa_stamping_india",       # Add as many public channels as you want
    "h1b_slots"
    # "another_channel_here",       # Uncomment and add more channels here
    # "yet_another_channel",
]
 
# ── KEYWORDS TO WATCH ───────────────────────────────────────────────────────
KEYWORDS = [
    "h4",
    "hyderabad", "hyd",
    "chennai", "mas",
    "slot", "available", "availability",
    "opening", "opened", "open",
    "appointment",
    "stamping",
]
 
# ── CLIENT SETUP ─────────────────────────────────────────────────────────────
client = TelegramClient("h4_monitor", API_ID, API_HASH)
 
def is_relevant(text: str) -> bool:
    """Return True if the message contains H4/slot related keywords."""
    if not text:
        return False
    text_lower = text.lower()
    has_slot     = any(k in text_lower for k in ["slot", "available", "availability", "opening", "appointment"])
    has_location = any(k in text_lower for k in ["hyderabad", "hyd", "chennai", "mas"])
    has_visa     = any(k in text_lower for k in ["h4", "h1", "visa", "stamping"])
    return (has_slot or has_location) and has_visa
 
async def send_alert(message_text: str, date: datetime, channel_name: str):
    """Forward a matched message as a formatted alert to Suneel."""
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
 
@client.on(events.NewMessage(chats=CHANNELS))
async def on_new_message(event):
    """Triggered on every new message in any of the monitored channels."""
    text = event.message.message
    channel_name = event.chat.username or event.chat.title
    if is_relevant(text):
        print(f"[MATCH] {datetime.now()} | @{channel_name} → {text[:80]}...")
        await send_alert(text, event.message.date, channel_name)
    else:
        print(f"[SKIP]  {datetime.now()} | @{channel_name} → {text[:60]}...")
 
async def startup_check():
    """On startup, check the last 20 messages from each channel."""
    print(f"🔍 Checking last 20 messages from {len(CHANNELS)} channel(s)...")
    for ch in CHANNELS:
        print(f"   → Checking @{ch}...")
        try:
            channel = await client.get_entity(ch)
            history = await client(GetHistoryRequest(
                peer=channel, limit=20, offset_date=None,
                offset_id=0, max_id=0, min_id=0, add_offset=0, hash=0
            ))
            matched = 0
            for msg in reversed(history.messages):
                if hasattr(msg, "message") and is_relevant(msg.message):
                    await send_alert(msg.message, msg.date, ch)
                    matched += 1
                    await asyncio.sleep(1)
            print(f"   ✅ @{ch} — {matched} relevant messages found.")
        except Exception as e:
            print(f"   ❌ Error checking @{ch}: {e}")
 
async def main():
    print("🤖 H4 Slot Alert Bot starting...")
    await client.start(bot_token=BOT_TOKEN)
    print(f"✅ Bot connected! Monitoring {len(CHANNELS)} channel(s):")
    for ch in CHANNELS:
        print(f"   → @{ch}")
 
    channel_list = "\n".join([f"  • @{ch}" for ch in CHANNELS])
    await client.send_message(
        YOUR_CHAT_ID,
        "✅ *H4 Slot Alert Bot is now LIVE!*\n\n"
        f"👁 Monitoring {len(CHANNELS)} channel(s):\n"
        f"{channel_list}\n\n"
        "📍 Locations: Hyderabad & Chennai\n"
        "🎯 Visa type: H4 slots\n\n"
        "I'll notify you the moment a slot is mentioned!",
        parse_mode="markdown"
    )
    await startup_check()
    print("👂 Listening for new messages...")
    await client.run_until_disconnected()
 
if __name__ == "__main__":
    asyncio.run(main())
 