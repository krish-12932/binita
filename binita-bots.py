#!/usr/bin/env python3
"""
Unlocker Pro v4.0 – Corporate-Grade Universal Search & Downloader
Author: BIBXMOD
Features: Token economy, Multi-Downloader, Global Search (no limits), Force Join,
          Auto-Delete (optimized for large files), Admin Mirror, Shortener Rotation.
"""

import asyncio
import json
import logging
import os
import random
import sys
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ------------------- MANDATORY IMPORT CHECK -------------------
MISSING_MODULES = []

try:
    from pyrogram import Client, filters, enums
    from pyrogram.types import (
        InlineKeyboardMarkup,
        InlineKeyboardButton,
        Message,
        CallbackQuery,
    )
    from pyrogram.errors import (
        FloodWait,
        UserNotParticipant,
        PeerIdInvalid,
    )
except ImportError:
    MISSING_MODULES.append("pyrogram")

try:
    from duckduckgo_search import DDGS
except ImportError:
    MISSING_MODULES.append("duckduckgo-search")

try:
    import aiohttp
except ImportError:
    MISSING_MODULES.append("aiohttp")

try:
    from flask import Flask
except ImportError:
    MISSING_MODULES.append("flask")

if MISSING_MODULES:
    print(f"❌ Missing critical modules: {', '.join(MISSING_MODULES)}")
    print("Run: pip install pyrogram tgcrypto duckduckgo-search aiohttp aiofiles flask")
    sys.exit(1)

# ------------------------- CONFIGURATION -------------------------
BOT_TOKEN = "8393455478:AAHyO-gxv0lKr4_T5a5N9lxoRVqEz7RzweQ"

# ✅ ADMIN IDs — Add as many as needed inside the curly braces, separated by commas
# Example: ADMIN_ID = {123456789, 987654321, 111222333}
ADMIN_ID = {8293859024, 7008609963}

LOG_CHANNEL = -1003827224603  # Negative ID
API_ID = 36637671
API_HASH = "97cded40ceae972550d1ff601234ae7d"
USER_SESSION_STRING = (
    "BQIvC-cAjyhu3Xfu75xeLT92-utMuQyu21c6ZJBAgumUwv_B6NgM2V60BJyYrtLUE-TBQA6BekaP5CT_Vw_-wLslo8279i78Ua9GlanTgcVTfOdjYg1ViM5u68UWo-0txqxlucZVZ09L88mbfhbZoZG2knhyhAueW2p92BZ4gAEUD3Sdw6gankukj5kHfHSnMRjMVdSktd-J82DLfH_tgkqcHg4AqxjOtjb0MOhce5APUdgCxqAL6i6lEeVV1JLCZ5BoX-vXvL_5xmRQZpjRqhJbe4Hi-2fFDgXGLmClX0VCPwX_IEOojdHHYDNEiE5XcXJomRwcBiFpnOiqloO3L8fhn1HeawAAAAG7rBMxAA"
)

# Shortener APIs (rotating)
SHORTENERS = [
    {"name": "TeraboxLinks", "key": "53e48453748d77d86255d1dda4adcc065872f154"},
    {"name": "NanoLinks", "key": "7bfb3d325568ee1f5119d63a2a07c0dfcd220646"},
    {"name": "ShareDisk", "key": "a0b225b1ae3ee443d6d37aa5a6a4bbb18e44c2f6"},
]

REQUIRED_CHANNELS = ["@NepaliMod", "@BIBXMOD", "@UnlockerProoo"]

# Token economy constants
WELCOME_TOKENS = 5
DOWNLOAD_COST = 5
REFERRAL_BONUS = 15
DAILY_BONUS = 2

# File auto-delete (optimized – starts after successful delivery)
AUTO_DELETE_DELAY = 30 * 60  # 30 minutes

# JSON database file
DB_FILE = "unlocker_db.json"

# ------------------------- DATABASE (JSON) -------------------------
class JsonDB:
    def __init__(self, path: str):
        self.path = path
        self.lock = asyncio.Lock()
        self._init_db()

    def _init_db(self):
        if not os.path.exists(self.path):
            with open(self.path, "w") as f:
                json.dump({"users": {}}, f, indent=2)

    async def _read(self) -> dict:
        async with self.lock:
            with open(self.path, "r") as f:
                return json.load(f)

    async def _write(self, data: dict):
        async with self.lock:
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)

    async def get_user(self, uid: int) -> Optional[dict]:
        data = await self._read()
        return data["users"].get(str(uid))

    async def update_user(self, uid: int, userdata: dict):
        data = await self._read()
        data["users"][str(uid)] = userdata
        await self._write(data)

    async def ensure_user(self, uid: int) -> dict:
        user = await self.get_user(uid)
        if user is None:
            user = {
                "tokens": 0,
                "referred_by": None,
                "referred_users": [],
                "last_daily": None,
                "banned": False,
            }
            await self.update_user(uid, user)
        return user

db = JsonDB(DB_FILE)

# ------------------------- CLIENTS -------------------------
app = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    sleep_threshold=10,
)

user_client = Client(
    ":memory:",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=USER_SESSION_STRING,
    sleep_threshold=10,
)

# ------------------------- LOGGING -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("UnlockerPro")

# ------------------------- GLOBAL STATES -------------------------
user_states: Dict[int, str] = {}  # state machine
search_cache: Dict[int, List[dict]] = {}  # user_id -> list of search result dicts

# ------------------------- UTILITY FUNCTIONS -------------------------
async def check_force_join(uid: int) -> Tuple[bool, Optional[str]]:
    """Returns (joined, missing_channel)"""
    for channel in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(channel, uid)
            if member.status in (
                enums.ChatMemberStatus.LEFT,
                enums.ChatMemberStatus.BANNED,
                enums.ChatMemberStatus.RESTRICTED,
            ):
                return False, channel
        except (UserNotParticipant, PeerIdInvalid):
            return False, channel
        except Exception as e:
            logger.warning(f"Force join check error for {channel}: {e}")
            return False, channel
    return True, None

async def force_join_reply(uid: int):
    buttons = [
        [InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch[1:]}")]
        for ch in REQUIRED_CHANNELS
    ]
    buttons.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_join")])
    txt = (
        "🔒 **Access Restricted**\n\n"
        "You must join all three channels to use this bot:\n"
        + "\n".join(f"👉 {ch}" for ch in REQUIRED_CHANNELS)
        + "\n\nAfter joining, click **I've Joined**."
    )
    try:
        await app.send_message(uid, txt, reply_markup=InlineKeyboardMarkup(buttons))
    except FloodWait as e:
        await asyncio.sleep(e.value)

async def log_to_channel(message: Message):
    """Mirror a message to the admin log channel."""
    try:
        await message.copy(LOG_CHANNEL)
    except Exception as e:
        logger.error(f"Log mirror failed: {e}")

async def schedule_auto_delete(chat_id: int, msg_id: int, delay: int = AUTO_DELETE_DELAY):
    """
    Delete a message after given delay.
    This is triggered AFTER the message is sent, so even large files are safe.
    """
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id, msg_id)
        logger.info(f"Auto-deleted message {msg_id} in chat {chat_id}")
    except Exception as e:
        logger.error(f"Auto-delete failed: {e}")

async def shorten_url(long_url: str) -> str:
    """Rotate through configured shortener APIs."""
    api_info = random.choice(SHORTENERS)
    # Different shorteners may have different endpoints; this is a generic approach.
    # Adjust if the actual API differs.
    api_url = f"https://{api_info['name'].lower()}.com/api"
    params = {"api": api_info["key"], "url": long_url}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params, timeout=10) as resp:
                data = await resp.json()
                if data.get("status") == "success":
                    return data.get("shortenedUrl", long_url)
                else:
                    raise Exception(data.get("message", "Unknown"))
    except Exception as e:
        logger.error(f"Shortener {api_info['name']} failed: {e}")
        return long_url  # fallback original URL

# ------------------------- SEARCH ENGINE (Unlimited, No Filter) -------------------------
async def perform_web_search(query: str) -> List[dict]:
    """
    Uses DuckDuckGo search without any restrictions.
    Returns list of dicts: {title, url, body}
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=10))  # Retrieves top 10, no filters
        return [{"title": r["title"], "url": r["href"], "body": r["body"]} for r in results]
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return []

# ------------------------- TERABOX DOWNLOADER -------------------------
async def terabox_direct_link(link: str) -> Optional[str]:
    """
    Extract direct download link from Terabox URL.
    Replace this with your own API endpoint.
    """
    api_endpoint = "https://terabox-dl.vercel.app/api"  # example
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_endpoint, params={"url": link}, timeout=30) as resp:
                data = await resp.json()
                if data.get("status") == "success":
                    return data.get("direct_link")
                return None
    except Exception as e:
        logger.error(f"Terabox error: {e}")
        return None

# ------------------------- TELEGRAM DOWNLOADER -------------------------
async def download_telegram_media(link: str) -> Optional[str]:
    """
    Download file from a Telegram message link (public/private) using user client.
    Returns local file path.
    """
    try:
        if "t.me/c/" in link:  # private supergroup
            parts = link.split("/")
            chat_id = int("-100" + parts[4])
            msg_id = int(parts[5])
        else:  # public
            parts = link.split("/")
            username = parts[3]
            msg_id = int(parts[4])
            chat = await user_client.get_chat(username)
            chat_id = chat.id

        msg = await user_client.get_messages(chat_id, msg_id)
        if not msg or not msg.media:
            return None
        file_path = await user_client.download_media(msg, in_memory=False)
        return file_path
    except Exception as e:
        logger.error(f"Telegram download failed: {e}")
        return None

# ------------------------- DECORATORS -------------------------
def private_only(func):
    async def wrapper(client, message):
        if message.chat.type != enums.ChatType.PRIVATE:
            await message.reply("⚠️ This bot works only in private messages.")
            return
        return await func(client, message)
    return wrapper

def access_required(func):
    """Ensure user passed force-join and is not banned."""
    async def wrapper(client, event):
        uid = event.from_user.id
        user = await db.ensure_user(uid)
        if user.get("banned"):
            await app.send_message(uid, "⛔ You are banned.")
            return
        joined, _ = await check_force_join(uid)
        if not joined:
            await force_join_reply(uid)
            return
        return await func(client, event)
    return wrapper

# ------------------------- START COMMAND -------------------------
@app.on_message(filters.command("start") & filters.private)
@private_only
@access_required
async def start_command(client, message: Message):
    uid = message.from_user.id
    user = await db.ensure_user(uid)

    # Handle referral
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            ref_id = int(args[1][3:])
            if ref_id != uid and user.get("referred_by") is None:
                referrer = await db.ensure_user(ref_id)
                if not referrer.get("banned"):
                    user["tokens"] += REFERRAL_BONUS
                    user["referred_by"] = ref_id
                    referrer["tokens"] += REFERRAL_BONUS
                    referrer.setdefault("referred_users", []).append(uid)
                    await db.update_user(uid, user)
                    await db.update_user(ref_id, referrer)
                    try:
                        await client.send_message(
                            ref_id, f"🎉 +{REFERRAL_BONUS} tokens! Someone joined via your link."
                        )
                    except:
                        pass
                    await message.reply(f"🎁 Referral bonus: +{REFERRAL_BONUS} tokens!")
        except:
            pass

    # Welcome gift for genuine new users (no tokens, no referrer)
    if user["tokens"] == 0 and user["referred_by"] is None:
        user["tokens"] = WELCOME_TOKENS
        await db.update_user(uid, user)
        await message.reply(f"🚀 Welcome! You received {WELCOME_TOKENS} free tokens.")

    # Build main menu
    tokens = user["tokens"]
    main_text = (
        f"👋 **Unlocker Pro v4.0**\n\n"
        f"🔹 Your tokens: **{tokens}**\n"
        "Select a service:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Terabox Downloader", callback_data="menu_terabox")],
        [InlineKeyboardButton("🌐 Global Web Search", callback_data="menu_search")],
        [InlineKeyboardButton("🤖 Telegram Downloader", callback_data="menu_tg_download")],
        [InlineKeyboardButton("👥 Refer & Earn", callback_data="menu_refer")],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="menu_daily")],
    ])
    await message.reply(main_text, reply_markup=keyboard, disable_web_page_preview=True)

# ------------------------- CALLBACK HANDLERS -------------------------
@app.on_callback_query(filters.regex("check_join"))
@access_required
async def check_join_callback(client, callback: CallbackQuery):
    joined, _ = await check_force_join(callback.from_user.id)
    if joined:
        await callback.edit_message_text("✅ Verified! Send /start to begin.")
    else:
        await callback.answer("You have not joined all channels yet.", show_alert=True)

@app.on_callback_query(filters.regex("^menu_"))
@access_required
async def menu_handler(client, callback: CallbackQuery):
    uid = callback.from_user.id
    data = callback.data
    user_states.pop(uid, None)

    if data == "menu_terabox":
        user_states[uid] = "terabox"
        await callback.edit_message_text(
            "📥 **Terabox Downloader**\nSend the Terabox share link.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_back")]])
        )
    elif data == "menu_search":
        user_states[uid] = "search"
        await callback.edit_message_text(
            "🌐 **Global Search**\nType any query (movies, apps, files...).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_back")]])
        )
    elif data == "menu_tg_download":
        user_states[uid] = "tg_download"
        await callback.edit_message_text(
            "🤖 **Telegram Downloader**\nSend a message link (e.g., https://t.me/xxx/123).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_back")]])
        )
    elif data == "menu_refer":
        user = await db.ensure_user(uid)
        ref_link = f"https://t.me/{client.me.username}?start=ref{uid}"
        txt = (
            f"👥 **Refer & Earn**\n\n"
            f"Your tokens: {user['tokens']}\n"
            f"Ref link:\n`{ref_link}`\n\n"
            f"Both get **{REFERRAL_BONUS} tokens**."
        )
        await callback.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_back")]]))
    elif data == "menu_daily":
        user = await db.ensure_user(uid)
        now = datetime.now()
        last = user.get("last_daily")
        if last and (now - datetime.fromisoformat(last)) < timedelta(hours=24):
            await callback.answer("⏳ Already claimed today.", show_alert=True)
            return
        user["tokens"] += DAILY_BONUS
        user["last_daily"] = now.isoformat()
        await db.update_user(uid, user)
        await callback.edit_message_text(
            f"🎁 +{DAILY_BONUS} tokens! Balance: {user['tokens']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_back")]])
        )
    elif data == "menu_back":
        await callback.message.delete()
        await start_command(client, callback.message)

# ------------------------- TEXT HANDLER (STATE BASED) -------------------------
@app.on_message(filters.text & filters.private & ~filters.command(["start", "broadcast", "ban", "unban", "addtokens", "stats"]))
@access_required
async def text_handler(client, message: Message):
    uid = message.from_user.id
    state = user_states.get(uid, "search")  # default to search if no state
    user_states[uid] = state

    if state == "search":
        await process_search(client, message)
    elif state == "terabox":
        await process_terabox(client, message)
    elif state == "tg_download":
        await process_tg_download(client, message)
    else:
        await message.reply("❌ Unknown state. Use /start.")

# ------------------------- PROCESSING FUNCTIONS -------------------------
async def process_search(client, message: Message):
    uid = message.from_user.id
    query = message.text.strip()
    if not query:
        await message.reply("Send a search query.")
        return

    temp = await message.reply("🔍 Searching globally (no limits)...")
    results = await perform_web_search(query)
    if not results:
        await temp.edit("No results found.")
        return

    search_cache[uid] = results
    buttons = []
    row = []
    for idx, res in enumerate(results, start=1):
        title = res["title"][:45]
        row.append(InlineKeyboardButton(f"{idx}. {title}", callback_data=f"openlink_{idx-1}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_back")])

    await temp.edit(
        f"**Results for:** `{query}`\nTap a link to open. Each direct link costs {DOWNLOAD_COST} tokens.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def process_terabox(client, message: Message):
    uid = message.from_user.id
    link = message.text.strip()
    if not link.startswith("http"):
        await message.reply("Invalid URL.")
        return

    temp = await message.reply("⏳ Fetching Terabox link...")
    direct = await terabox_direct_link(link)
    if not direct:
        await temp.edit("❌ Could not retrieve download link. The service may be down.")
        return

    user = await db.ensure_user(uid)
    if user["tokens"] >= DOWNLOAD_COST:
        user["tokens"] -= DOWNLOAD_COST
        await db.update_user(uid, user)
        sent = await temp.edit(f"✅ **Direct Link** (ad-free)\n`{direct}`\n-{DOWNLOAD_COST} tokens")
    else:
        short = await shorten_url(direct)
        sent = await temp.edit(f"🔗 **Ad-Supported Link**\n{short}\nEarn tokens to skip ads.")

    # Mirror and schedule deletion
    await log_to_channel(sent)
    asyncio.create_task(schedule_auto_delete(uid, sent.id))

async def process_tg_download(client, message: Message):
    uid = message.from_user.id
    link = message.text.strip()
    if not link.startswith("https://t.me/"):
        await message.reply("Invalid Telegram link.")
        return

    user = await db.ensure_user(uid)
    if user["tokens"] < DOWNLOAD_COST:
        await message.reply(f"⛔ You need {DOWNLOAD_COST} tokens. Use /daily or refer friends.")
        return

    temp = await message.reply("⬇️ Downloading from Telegram...")
    file_path = await download_telegram_media(link)
    if not file_path:
        await temp.edit("❌ Download failed. Check link or user client access.")
        return

    try:
        sent = await client.send_document(
            uid, file_path, caption=f"⬆️ -{DOWNLOAD_COST} tokens | Auto-delete 30 min"
        )
        user["tokens"] -= DOWNLOAD_COST
        await db.update_user(uid, user)
        await log_to_channel(sent)
        asyncio.create_task(schedule_auto_delete(uid, sent.id))
        await temp.delete()
    except Exception as e:
        await temp.edit(f"❌ Upload error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# ------------------------- OPEN LINK FROM SEARCH -------------------------
@app.on_callback_query(filters.regex(r"^openlink_(\d+)"))
@access_required
async def open_search_link(client, callback: CallbackQuery):
    uid = callback.from_user.id
    idx = int(callback.matches[0].group(1))
    results = search_cache.get(uid)
    if not results or idx >= len(results):
        await callback.answer("Search expired. Please search again.", show_alert=True)
        return

    url = results[idx]["url"]
    user = await db.ensure_user(uid)

    if user["tokens"] >= DOWNLOAD_COST:
        user["tokens"] -= DOWNLOAD_COST
        await db.update_user(uid, user)
        await callback.edit_message_text(
            f"✅ **Ad-Free Link**\n\n{url}\n\n-{DOWNLOAD_COST} tokens",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_back")]]),
            disable_web_page_preview=True,
        )
        sent = callback.message
    else:
        short = await shorten_url(url)
        await callback.edit_message_text(
            f"🔗 **Ad-Supported Link**\n\n{short}\n\nGet tokens to unlock direct.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_back")]]),
            disable_web_page_preview=True,
        )
        sent = callback.message

    await log_to_channel(sent)
    asyncio.create_task(schedule_auto_delete(uid, sent.id))

# ------------------------- ADMIN COMMANDS -------------------------
@app.on_message(filters.command("broadcast") & filters.user(list(ADMIN_ID)))
async def broadcast(client, message: Message):
    if len(message.text.split()) < 2:
        return await message.reply("Usage: /broadcast <text>")
    text = message.text.split(maxsplit=1)[1]
    data = await db._read()
    users = data.get("users", {})
    success = 0
    for uid_str in list(users.keys()):
        try:
            await client.send_message(int(uid_str), text)
            success += 1
            await asyncio.sleep(0.05)
        except:
            continue
    await message.reply(f"✅ Broadcast to {success}/{len(users)} users.")

@app.on_message(filters.command("ban") & filters.user(list(ADMIN_ID)))
async def ban_user(client, message: Message):
    try:
        uid = int(message.text.split()[1])
    except:
        return await message.reply("Usage: /ban <user_id>")
    user = await db.ensure_user(uid)
    user["banned"] = True
    await db.update_user(uid, user)
    await message.reply(f"🚫 Banned {uid}.")

@app.on_message(filters.command("unban") & filters.user(list(ADMIN_ID)))
async def unban_user(client, message: Message):
    try:
        uid = int(message.text.split()[1])
    except:
        return await message.reply("Usage: /unban <user_id>")
    user = await db.ensure_user(uid)
    user["banned"] = False
    await db.update_user(uid, user)
    await message.reply(f"✅ Unbanned {uid}.")

@app.on_message(filters.command("addtokens") & filters.user(list(ADMIN_ID)))
async def add_tokens(client, message: Message):
    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply("Usage: /addtokens <user_id> <amount>")
    try:
        uid, amount = int(parts[1]), int(parts[2])
    except:
        return await message.reply("Invalid numbers.")
    user = await db.ensure_user(uid)
    user["tokens"] += amount
    await db.update_user(uid, user)
    await message.reply(f"✅ Added {amount} tokens to {uid}. Balance: {user['tokens']}")

@app.on_message(filters.command("stats") & filters.user(list(ADMIN_ID)))
async def stats(client, message: Message):
    data = await db._read()
    total_users = len(data.get("users", {}))
    await message.reply(f"📊 Total users: {total_users}")

# ------------------------- FLASK KEEP-ALIVE SERVER -------------------------
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "✅ Unlocker Pro is running!", 200

@flask_app.route("/health")
def health():
    return "OK", 200

def run_flask():
    """Run Flask server in a background thread."""
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_keep_alive():
    """Start Flask in a daemon thread so it dies with the main process."""
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info(f"🌐 Flask keep-alive server started on port {os.environ.get('PORT', 8080)}")

# ------------------------- SELF-PING TASK -------------------------
async def self_ping():
    """
    Ping the /health endpoint every 10 minutes to prevent
    Render / Railway free-tier from sleeping.
    """
    port = int(os.environ.get("PORT", 8080))
    url = f"http://localhost:{port}/health"
    await asyncio.sleep(30)  # small delay before first ping
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    logger.info(f"🔄 Self-ping → {resp.status}")
        except Exception as e:
            logger.warning(f"Self-ping failed: {e}")
        await asyncio.sleep(10 * 60)  # 10 minutes

# ------------------------- MAIN ENTRY POINT -------------------------
async def main():
    # Start Flask keep-alive server in background thread
    start_keep_alive()

    # Start self-ping loop
    asyncio.create_task(self_ping())

    logger.info("Starting user client...")
    await user_client.start()
    logger.info("Starting bot client...")
    await app.start()
    logger.info("✅ Unlocker Pro v4.0 is live!")
    # Block forever
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    finally:
        # Cleanup if any file left
        pass