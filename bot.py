import os
import re
import io
import json
import copy
import base64
import struct
import asyncio
import time
import zipfile
import tempfile
import shutil
import hashlib
import ssl
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from collections import defaultdict

from telethon import TelegramClient, events, Button
from telethon.tl import types
from telethon.errors import FloodWaitError, UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.sessions import StringSession

# ==================== CONFIG ====================
# Values can be overridden via environment variables for hosting (Replit/Railway).
# Defaults below are identical to the original config.
API_ID = int(os.environ.get("API_ID", "31663810"))
API_HASH = os.environ.get("API_HASH", "c26da3d5cb8b74057b2a90aacd6d0931")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8312438596:AAEtb9j683JJPBxedDcr9oKGUOOUZ3KRfeI")
OWNER_ID = int(os.environ.get("OWNER_ID", "8327850869"))
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "@OwAtom")
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "-1004313199843"))
LOG_CHANNEL_URL = os.environ.get("LOG_CHANNEL_URL", "https://t.me/jhgghhlok")
APK_ARCHIVE_CHANNEL = int(os.environ.get("APK_ARCHIVE_CHANNEL", "-1003776813052"))
APK_ARCHIVE_CHANNEL_URL = os.environ.get("APK_ARCHIVE_CHANNEL_URL", "https://t.me/OowXD")
BRAND_NAME = os.environ.get("BRAND_NAME", "MARC")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "@Kkftinbot")

# Force Subscribe Channel
FSUB_CHANNEL = os.environ.get("FSUB_CHANNEL", "@owabyss")
FSUB_CHANNEL_URL = os.environ.get("FSUB_CHANNEL_URL", "https://t.me/OwAbyss")

# Multi-Scan Concurrency Limits (exact batch of 5 parallel scans, others queued)
MAX_CONCURRENT_PER_USER = int(os.environ.get("MAX_CONCURRENT_PER_USER", "5"))
GLOBAL_CONCURRENT_LIMIT = int(os.environ.get("GLOBAL_CONCURRENT_LIMIT", "5"))
GLOBAL_SCAN_SEMAPHORE = asyncio.Semaphore(GLOBAL_CONCURRENT_LIMIT)

# Premium emoji IDs (fallback to unicode if not available)
EMOJIS = {
    "fire": "🔥",
    "check": "✅",
    "cross": "❌",
    "warning": "⚠️",
    "package": "📦",
    "globe": "🌐",
    "id_card": "🆔",
    "lock": "🔒",
    "key": "🔑",
    "phone": "📱",
    "info": "ℹ️",
    "gear": "⚙️",
    "chart": "📊",
    "folder": "📁",
    "search": "🔍",
    "rocket": "🚀",
    "zap": "⚡",
    "shield": "🛡️",
    "bucket": "🪣",
    "bar_chart": "📊",
    "user": "👤",
    "calendar": "📅",
    "clock": "🕐",
    "timer": "⏱",
    "star": "⭐",
    "diamond": "💎",
    "link": "🔗",
}

def styled_button(text: str, data=None, url: str = None, color: str = None):
    """
    Creates Telegram buttons with native background colors:
    color='primary' -> Teal / Blue background
    color='danger'  -> Red / Maroon background
    color='success' -> Green background
    """
    if url:
        return Button.url(text, url, style=color)
    else:
        return Button.inline(text, data, style=color)

ADMIN_IDS = set([OWNER_ID, 6217522461, 8219398815, 7812349806])
if os.environ.get("ADMIN_IDS"):
    for a in os.environ.get("ADMIN_IDS").split(","):
        if a.strip().isdigit():
            ADMIN_IDS.add(int(a.strip()))

def ensure_admin_menu(uid: int):
    """Dynamically register admin commands menu for this admin on Telegram."""
    if uid not in ADMIN_IDS:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands"
        payload = {
            "commands": [
                {"command": "admin", "description": "👑 Open Admin Control Panel"},
                {"command": "maint", "description": "⚙️ Toggle Maintenance Mode"},
                {"command": "broadcast", "description": "📢 Broadcast Announcement"},
                {"command": "banned", "description": "🚫 View Banned Users"},
                {"command": "ban", "description": "🚫 Ban a User ID"},
                {"command": "unban", "description": "✅ Unban a User ID"},
                {"command": "firebase", "description": "🔍 Probe Firebase Database URL"},
                {"command": "start", "description": "⚡ Main Menu & Scan"},
                {"command": "help", "description": "📖 Commands & Guide"},
                {"command": "stats", "description": "📊 Bot Statistics"},
                {"command": "history", "description": "📂 My APK Scan History"},
                {"command": "myid", "description": "🆔 My Profile & ID"}
            ],
            "scope": {"type": "chat", "chat_id": uid}
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

        def _send():
            try:
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass

        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_in_executor(None, _send)
    except Exception:
        pass

# ==================== DATA STORAGE ====================
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd(), "users.json")

def load_users():
    users = set([OWNER_ID])
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for u in data:
                        if str(u).isdigit() or isinstance(u, int):
                            users.add(int(u))
    except Exception:
        pass
    return users

USER_STATS = defaultdict(lambda: {"scans": 0, "first_seen": None, "last_seen": None})
SCAN_HISTORY = defaultdict(list)  # user_id -> list of scan results
BOT_STATS = {
    "total_scans": 0,
    "total_users": load_users(),
    "total_scan_time": 0.0,
    "start_time": datetime.now()
}

def save_user(uid):
    if not uid:
        return
    try:
        uid = int(uid)
    except (ValueError, TypeError):
        return
    if uid not in BOT_STATS["total_users"]:
        BOT_STATS["total_users"].add(uid)
        try:
            tmp_file = USERS_FILE + ".tmp"
            with open(tmp_file, "w") as f:
                json.dump(list(BOT_STATS["total_users"]), f)
            os.replace(tmp_file, USERS_FILE)
        except Exception:
            pass

BANNED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd(), "banned.json")

def load_banned():
    banned = set()
    try:
        if os.path.exists(BANNED_FILE):
            with open(BANNED_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for u in data:
                        if str(u).isdigit() or isinstance(u, int):
                            banned.add(int(u))
    except Exception:
        pass
    return banned

BANNED_USERS = load_banned()
MAINTENANCE_MODE = False

# ─── TeleCore Sliding Window Anti-Flood & Maintenance Mode Guard ───
_user_last_action_ts = {}
_user_last_warn_ts = {}
RATE_LIMIT_SECONDS = float(os.environ.get("RATE_LIMIT_SECONDS", "1.0"))
RATE_LIMIT_ENABLED = True

# ─── Atomic Event Deduplicator across Telethon & Bot API ───
PROCESSED_EVENT_KEYS = {}

def claim_event(key: str) -> bool:
    """
    Atomic event deduplicator across Telethon MTProto and Bot API Poller.
    Returns True if this is the first time seeing this event.
    Returns False if already claimed or in-flight.
    """
    if not key:
        return True
    now = time.time()
    # Prune keys older than 10 minutes
    if len(PROCESSED_EVENT_KEYS) > 3000:
        cutoff = now - 600
        for k in list(PROCESSED_EVENT_KEYS.keys()):
            if PROCESSED_EVENT_KEYS[k] < cutoff:
                PROCESSED_EVENT_KEYS.pop(k, None)
    if key in PROCESSED_EVENT_KEYS:
        return False
    PROCESSED_EVENT_KEYS[key] = now
    return True

async def telecore_guard(event) -> bool:
    """
    TeleCore Sliding Window Anti-Flood & Maintenance Mode Guard with Atomic Deduplication.
    Returns True if allowed to proceed, False otherwise.
    """
    uid = getattr(event, "sender_id", None)
    if not uid:
        return False

    # 0. Atomic Deduplication check between Telethon MTProto and Bot API Poller
    if isinstance(event, events.CallbackQuery.Event):
        cb_data = getattr(event, "data", b"")
        cb_data_str = cb_data.decode('utf-8', 'ignore') if isinstance(cb_data, bytes) else str(cb_data)
        cb_key = f"cb:{uid}:{getattr(event, 'message_id', None)}:{cb_data_str}"
        if not claim_event(cb_key):
            return False
    elif isinstance(event, events.NewMessage.Event):
        chat_id = getattr(event, "chat_id", None)
        msg_id = getattr(event, "id", None)
        if chat_id and msg_id:
            if not claim_event(f"msg:{chat_id}:{msg_id}"):
                return False

    is_admin = (uid in ADMIN_IDS) or (uid == OWNER_ID)
    now = time.time()

    # 1. Ban Check
    if uid in BANNED_USERS and not is_admin:
        return False

    # 2. Maintenance Mode Guard (Super Admin / Admins Only)
    if MAINTENANCE_MODE and not is_admin:
        last_warn = _user_last_warn_ts.get(uid, 0.0)
        if (now - last_warn) > 3.0:
            _user_last_warn_ts[uid] = now
            maint_msg = (
                "🛠️ **Maintenance Mode Active**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "Bot is currently undergoing scheduled system updates.\n"
                "Only Bot Owners/Admins have access right now.\n\n"
                "⏳ *Please try again later. Thank you!*"
            )
            if hasattr(event, "answer") and callable(event.answer):
                try:
                    await event.answer("🛠️ Maintenance Mode active! Please wait.", alert=True)
                except Exception:
                    pass
            elif hasattr(event, "reply") and callable(event.reply):
                try:
                    await event.reply(maint_msg)
                except Exception:
                    pass
        return False

    # 3. Sliding Window Anti-Flood Rate Limiter
    if RATE_LIMIT_ENABLED and not is_admin:
        last_action = _user_last_action_ts.get(uid, 0.0)
        if (now - last_action) < RATE_LIMIT_SECONDS:
            last_warn = _user_last_warn_ts.get(uid, 0.0)
            if (now - last_warn) > 2.0:
                _user_last_warn_ts[uid] = now
                if hasattr(event, "answer") and callable(event.answer):
                    try:
                        await event.answer("⚠️ Slow down! (Anti-Flood Protection)", alert=False)
                    except Exception:
                        pass
                elif hasattr(event, "reply") and callable(event.reply):
                    try:
                        await event.reply("⚠️ **Slow Down!** Requests are being sent too quickly. Please wait 1 second between actions.")
                    except Exception:
                        pass
            return False
        _user_last_action_ts[uid] = now

    return True

def save_banned():
    try:
        tmp_file = BANNED_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(list(BANNED_USERS), f)
        os.replace(tmp_file, BANNED_FILE)
    except Exception:
        pass

# Force subscribe channel membership verification
async def check_fsub(uid):
    """Returns True if user has joined required channel or is exempt, False otherwise."""
    if uid in ADMIN_IDS:
        return True
    if not FSUB_CHANNEL:
        return True
    try:
        channel_entity = await client.get_input_entity(FSUB_CHANNEL)
        await client(GetParticipantRequest(channel=channel_entity, participant=uid))
        return True
    except UserNotParticipantError:
        return False
    except Exception:
        # Fallback to True if channel resolution fails or bot is not admin in channel
        return True

def get_fsub_buttons():
    return [
        [styled_button("📢 Join Official Channel", url=FSUB_CHANNEL_URL, color="primary")],
        [styled_button("✅ Verify Membership", b"check_fsub_btn", color="success")]
    ]

def get_fsub_message(first_name="User"):
    return (
        f"⚠️ **Access Restricted!**\n\n"
        f"Hey **{first_name}**, to use **{BRAND_NAME} Firebase Extractor**, you must join our official channel first.\n\n"
        f"📢 **Channel:** [{FSUB_CHANNEL}]({FSUB_CHANNEL_URL})\n\n"
        f"Join the channel using the button below, then click **I've Joined** to unlock the bot!"
    )

# Cache of completed scans keyed by APK sha1 — identical re-scans skip parsing.
SCAN_CACHE = {}
MAX_CACHE_ENTRIES = 20
URL_CACHE = {}

# Per-user queue and concurrency tracking
USER_QUEUE = {}
PENDING = {}
USER_ACTIVE_SCANS = {}
GLOBAL_ACTIVE_SCANS = 0

# ==================== SPEED / SAFETY SETTINGS ====================
MAX_UPLOAD_SIZE = 75 * 1024 * 1024     # reject APK uploads larger than 75MB to prevent container OOM
MAX_SCAN_FILE_SIZE = 2 * 1024 * 1024   # skip plaintext files larger than 2MB
MAX_AXML_SIZE = 4 * 1024 * 1024        # binary XML files up to 4MB
MAX_ARSC_SIZE = 16 * 1024 * 1024       # resources.arsc up to 16MB
MAX_DEX_SIZE = 24 * 1024 * 1024        # classes.dex up to 24MB (prevent OOM spikes on Railway)
MAX_DEX_STRINGS = 35000                # cap strings decoded per dex file
MAX_POOL_STRINGS = 30000               # cap strings per binary string pool
MAX_CORPUS_STRINGS = 50000             # global cap for extracted string corpus
MAX_ARSC_CHUNKS = 15000                # safety cap for arsc chunk walker
PROGRESS_EDIT_INTERVAL = 0.8           # seconds between progress-message edits

# ==================== ANDROID BINARY XML & RESSTRINGPOOL HELPERS ====================
def _axml_strings(data, cap=MAX_POOL_STRINGS):
    """Extract readable strings from a binary XML / ResStringPool string pool."""
    if not data or len(data) < 8:
        return []
    try:
        pool_data = data
        ctype, hsize = struct.unpack_from('<HH', pool_data, 0)
        # If binary XML (0x0003), the string pool chunk (0x0001) follows the XML header (usually offset 8)
        if ctype == 0x0003:
            pool_data = data[hsize:]
            if len(pool_data) < 28:
                return []
            ctype, hsize = struct.unpack_from('<HH', pool_data, 0)

        # If still not 0x0001, scan for embedded 0x0001 header in the first 512 bytes
        if ctype != 0x0001:
            found = False
            for offset in range(0, min(len(data) - 28, 512), 4):
                c_t, h_s = struct.unpack_from('<HH', data, offset)
                if c_t == 0x0001 and h_s >= 28:
                    pool_data = data[offset:]
                    ctype, hsize = c_t, h_s
                    found = True
                    break
            if not found:
                return []

        if len(pool_data) < 28:
            return []

        string_count, _style_count, flags, strings_start, _styles_start = struct.unpack_from('<IIIII', pool_data, 8)
        if not string_count or strings_start == 0 or strings_start > len(pool_data):
            return []
        string_count = min(string_count, cap)
        utf8 = bool(flags & 0x00000100)
        strings = []
        for i in range(string_count):
            off_pos = hsize + 4 * i
            if off_pos + 4 > len(pool_data):
                break
            (off,) = struct.unpack_from('<I', pool_data, off_pos)
            pos = strings_start + off
            if pos >= len(pool_data):
                continue
            try:
                if utf8:
                    b = pool_data[pos]; pos += 1
                    if b & 0x80: pos += 1
                    b = pool_data[pos]; pos += 1
                    if b & 0x80:
                        u8len = ((b & 0x7F) << 8) | pool_data[pos]
                        pos += 1
                    else:
                        u8len = b
                    end = min(pos + u8len, len(pool_data))
                    s = pool_data[pos:end].decode('utf-8', errors='ignore')
                else:
                    slen = struct.unpack_from('<H', pool_data, pos)[0]
                    pos += 2
                    if slen & 0x8000:
                        slen = ((slen & 0x7FFF) << 16) | struct.unpack_from('<H', pool_data, pos)[0]
                        pos += 2
                    end = min(pos + slen * 2, len(pool_data))
                    s = pool_data[pos:end].decode('utf-16-le', errors='ignore')
                if s:
                    strings.append(s)
            except Exception:
                continue
        return strings
    except Exception:
        return []


# ==================== DEX STRING TABLE PARSER ====================
class DexStrings:
    """Extract the string table from a .dex file."""
    HEADER_FMT = '<8sI20sIIIIIIII'
    HEADER_SIZE = 0x70

    def __init__(self, data):
        self.data = data

    def _u(self, off, fmt='<I'):
        try:
            return struct.unpack_from(fmt, self.data, off)[0]
        except struct.error:
            return 0

    def get_strings(self, cap=MAX_DEX_STRINGS):
        try:
            if len(self.data) < self.HEADER_SIZE:
                return
            (magic, _checksum, _sig, _fsize, _hsize, _endsize,
             _link_size, _link_off, _map_off, string_ids_size, string_ids_off) = \
                struct.unpack_from(self.HEADER_FMT, self.data, 0)
            if magic[:4] != b'dex\n' or string_ids_size == 0 or string_ids_off == 0:
                return
            string_ids_size = min(string_ids_size, cap)
            count = 0
            for i in range(string_ids_size):
                data_off = self._u(string_ids_off + i * 4)
                if not data_off or data_off >= len(self.data):
                    continue
                pos = data_off
                try:
                    # Proper ULEB128 variable-length integer decoding
                    size = 0
                    shift = 0
                    while True:
                        b = self.data[pos]
                        pos += 1
                        size |= (b & 0x7F) << shift
                        if not (b & 0x80):
                            break
                        shift += 7
                        if shift > 28:
                            break
                except IndexError:
                    continue
                if size <= 0 or size > 0x100000:
                    continue
                end = self.data.find(b'\x00', pos)
                if end == -1 or end > pos + 131072:
                    continue
                try:
                    s = self.data[pos:end].decode('utf-8', errors='ignore')
                except Exception:
                    continue
                if s:
                    count += 1
                    yield s
                    if count >= cap:
                        break
        except Exception:
            return


# ==================== ANDROID RESOURCE TABLE (resources.arsc) PARSER ====================
class ArscStrings:
    """Walk resources.arsc to extract all strings across all string pool chunks."""

    def __init__(self, data):
        self.data = data

    def get_pairs(self, cap=MAX_ARSC_CHUNKS):
        pairs = []
        try:
            d = self.data
            n = len(d)
            if n < 12:
                return pairs
            # Scan for all ResStringPoolHeader chunks (0x0001) in resources.arsc
            for i in range(0, n - 28, 4):
                ctype, hsize, csize = struct.unpack_from('<HHI', d, i)
                if ctype == 0x0001 and 28 <= hsize <= csize and i + csize <= n:
                    chunk_strings = _axml_strings(d[i:i + csize])
                    if chunk_strings:
                        pairs.extend(chunk_strings)
                        if len(pairs) >= cap:
                            break
        except Exception:
            pass
        return pairs


def safe_zip_read(z, entry_name_or_info, max_size=None):
    """Safely read an entry from a ZipFile, bypassing Bad CRC-32 errors caused by APK anti-analysis/tampering."""
    try:
        if max_size is not None:
            info = z.getinfo(entry_name_or_info) if isinstance(entry_name_or_info, str) else entry_name_or_info
            if info.file_size > max_size:
                return None
        try:
            return z.read(entry_name_or_info)
        except zipfile.BadZipFile:
            with z.open(entry_name_or_info, 'r') as fp:
                if hasattr(fp, '_expected_crc'):
                    fp._expected_crc = None
                return fp.read()
    except Exception:
        return None


# ==================== ADVANCED APK SCANNER & DEOBFUSCATION ENGINE ====================
class APKScanner:
    """
    High-performance, deep static analysis engine for Android APKs.
    Features:
      - Byte-level fast heuristic pre-filtering (< 20ms)
      - Binary XML (AXML) & Android Resource Table (ARSC) parser
      - Multi-DEX string pool reconstruction & lazy decoding
      - Multi-layer recursive Base64, XOR, Hex, URL, and reversed string deobfuscation
      - Hidden asset, dropper payload, and raw asset archive inspector
      - Native library (.so) ELF string and C2 scraper
      - Extraction of Firebase RTDB, Firestore, Google APIs, Telegram C2 bots, Webhooks,
        HTTP C2 gates, and SMS forward destination phone numbers.
    """

    BYTE_PRESCAN_PATTERNS = [
        (re.compile(rb'https?://[a-zA-Z0-9_-]+(?:-default-rtdb)?\.(?:[a-z0-9-]+\.)?(?:firebaseio\.com|firebasedatabase\.app)', re.I), 'firebase'),
        (re.compile(rb'AIza[0-9A-Za-z_-]{30,40}'), 'google_api_key'),
        (re.compile(rb'\b\d{8,11}:[a-zA-Z0-9_-]{35}\b'), 'telegram_token'),
        (re.compile(rb'https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+'), 'discord_webhook'),
    ]

    def __init__(self, apk_path):
        self.apk_path = apk_path
        self.results = {
            "filename": os.path.basename(apk_path),
            "package": None,
            "app_name": None,
            "version": None,
            "build_code": None,
            "packer": None,
            "firebase": {},
            "api_credentials": {},
            "telegram_c2": {},
            "webhooks": [],
            "c2_endpoints": [],
            "forward_phones": [],
            "device_stats": {},
            "errors": []
        }

    def scan(self):
        key = _hash_file(self.apk_path)
        if key and key in SCAN_CACHE:
            cached = SCAN_CACHE[key]
            cached.setdefault("scan_time", None)
            return copy.copy(cached)

        try:
            with zipfile.ZipFile(self.apk_path, 'r') as z:
                manifest_entry = None
                google_services_entry = None
                arsc_entry = None
                dex_entries = []
                other_code_entries = []
                native_entries = []
                asset_entries = []

                # Single-pass entry classification
                for info in z.infolist():
                    name = info.filename
                    low = name.lower()
                    if low.endswith('androidmanifest.xml'):
                        manifest_entry = name
                    elif low == 'google-services.json' or low.endswith('/google-services.json'):
                        google_services_entry = name
                    elif low == 'resources.arsc':
                        arsc_entry = name
                    elif low.endswith('.dex'):
                        dex_entries.append(name)
                    elif low.endswith('.so'):
                        native_entries.append(name)
                    elif low.startswith(('assets/', 'res/raw/')) and not low.endswith(('.png', '.jpg', '.webp', '.ttf', '.otf', '.mp3', '.ogg')):
                        asset_entries.append(name)
                    elif low.endswith(('.json', '.txt', '.properties', '.smali', '.xml', '.mf')):
                        other_code_entries.append(name)

                # 1. Android Manifest (AXML)
                if manifest_entry:
                    self._extract_manifest_entry(z, manifest_entry)

                # 2. Structural google-services.json
                if google_services_entry:
                    try:
                        raw_gs = safe_zip_read(z, google_services_entry)
                        if raw_gs:
                            self._extract_google_services(raw_gs)
                    except Exception:
                        pass

                # 3. Android Resource Table (ARSC)
                if arsc_entry:
                    try:
                        raw_arsc = safe_zip_read(z, arsc_entry, MAX_ARSC_SIZE)
                        if raw_arsc:
                            arsc_strs = ArscStrings(raw_arsc).get_pairs()
                            for s in arsc_strs:
                                self._extract_all_patterns(s)
                            if not self.results.get("app_name"):
                                for s in arsc_strs:
                                    if s.lower().startswith(('app_name', 'appname')):
                                        parts = s.split('=', 1)
                                        val = parts[1].strip() if len(parts) == 2 else ''
                                        if 1 <= len(val) <= 40 and not re.match(r'^[\w.]+$', val) and \
                                                'behavior' not in val.lower() and not val.lower().startswith('app'):
                                            self.results["app_name"] = val
                                            break
                    except Exception:
                        pass

                # 4. Multi-DEX Full Scan (all classes.dex, classes2.dex, etc.)
                for dex_name in dex_entries:
                    if self.results["firebase"].get("db_url") and self.results["api_credentials"].get("google_api_key"):
                        break
                    try:
                        data = safe_zip_read(z, dex_name, MAX_DEX_SIZE)
                        if data:
                            # Fast raw-byte pattern sweep
                            for pat, _ in self.BYTE_PRESCAN_PATTERNS:
                                for m in pat.finditer(data):
                                    self._extract_all_patterns(m.group(0).decode('utf-8', errors='ignore'))
                            # Deep DEX string pool walker (only if credentials not yet found)
                            if not (self.results["firebase"].get("db_url") and self.results["api_credentials"].get("google_api_key")):
                                for s in DexStrings(data).get_strings(cap=MAX_DEX_STRINGS):
                                    self._extract_all_patterns(s)
                                    if self.results["firebase"].get("db_url") and self.results["api_credentials"].get("google_api_key"):
                                        break
                    except Exception:
                        pass

                # 5. Plaintext configs, smali & JSON files
                if not (self.results["firebase"].get("db_url") and self.results["api_credentials"].get("google_api_key")):
                    for code_name in other_code_entries[:30]:
                        try:
                            raw = safe_zip_read(z, code_name, MAX_DEX_SIZE)
                            if raw:
                                text = raw.decode('utf-8', errors='ignore')
                                self._extract_all_patterns(text)
                                if self.results["firebase"].get("db_url") and self.results["api_credentials"].get("google_api_key"):
                                    break
                        except Exception:
                            pass

                # 6. Native shared libraries (.so ELF string scraping)
                if not self.results["firebase"].get("db_url"):
                    for so_name in native_entries[:6]:
                        try:
                            raw = safe_zip_read(z, so_name, 8 * 1024 * 1024)
                            if raw:
                                for pat, _ in self.BYTE_PRESCAN_PATTERNS:
                                    for m in pat.finditer(raw):
                                        self._extract_all_patterns(m.group(0).decode('utf-8', errors='ignore'))
                                for s in re.findall(rb'[\x20-\x7E]{6,}', raw[:2 * 1024 * 1024]):
                                    try:
                                        self._extract_all_patterns(s.decode('utf-8', errors='ignore'))
                                        if self.results["firebase"].get("db_url"):
                                            break
                                    except Exception:
                                        pass
                                if self.results["firebase"].get("db_url"):
                                    break
                        except Exception:
                            pass

                # 7. Hidden Asset, Droppers & Deep Deobfuscation (Base64 recursive, XOR, Hex, Inversion)
                # If Firebase credentials already found, skip expensive asset deobfuscation for max speed
                if not self.results["firebase"].get("db_url"):
                    for name in (asset_entries + other_code_entries)[:40]:
                        try:
                            raw = safe_zip_read(z, name, 2 * 1024 * 1024)
                            if raw:
                                # Check for embedded DEX inside assets
                                if raw.startswith(b'dex\n'):
                                    try:
                                        for s in DexStrings(raw).get_strings():
                                            self._extract_all_patterns(s)
                                    except Exception:
                                        pass

                                # Multi-layer deobfuscation
                                self._deobfuscate_base64_recursive(raw)
                                self._deobfuscate_hex(raw)
                                self._deobfuscate_reversed(raw)
                                self._deobfuscate_xor(raw)
                                if self.results["firebase"].get("db_url"):
                                    break
                        except Exception:
                            pass

                # 8. Comprehensive Packer Detection
                self._detect_packer(z)

        except Exception as e:
            self.results["errors"].append(str(e))

        if key:
            SCAN_CACHE[key] = self.results
            if len(SCAN_CACHE) > MAX_CACHE_ENTRIES:
                oldest = next(iter(SCAN_CACHE))
                del SCAN_CACHE[oldest]

        return self.results

    def _extract_manifest_entry(self, z, manifest_name):
        """Extract package info from AndroidManifest.xml."""
        try:
            manifest_data = safe_zip_read(z, manifest_name, MAX_AXML_SIZE)

            if not manifest_data:
                return

            strings = _axml_strings(manifest_data)
            if strings:
                for s in strings:
                    self._extract_all_patterns(s)
                # App label
                if not self.results.get("app_name"):
                    for s in strings:
                        if 2 <= len(s) <= 40 and re.match(r'^[a-zA-Z][\w\s&.\-()]*$', s) and \
                                not re.fullmatch(r'[\w.]+', s) and not s.lower().startswith(('uses-', 'android', 'androidx', 'com.', 'lib', 'meta-')) and ' ' in s:
                            self.results["app_name"] = s
                            break
                # Package name
                ignore_pkgs = ('android.', 'androidx.', 'kotlin.', 'kotlinx.', 'java.', 'javax.', 'com.google.', 'com.android.')
                for s in strings:
                    if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+', s) and \
                            'firebase' not in s.lower() and not s.startswith(ignore_pkgs):
                        self.results["package"] = s
                        break
                # Version name
                for s in strings:
                    if re.fullmatch(r'\d+(\.\d+)+[0-9A-Za-z._-]*', s):
                        if s != self.results.get("package") and not s.startswith('android'):
                            self.results["version"] = s
                            break
            else:
                text = manifest_data.decode('utf-8', errors='ignore')
                self._extract_all_patterns(text)

            if not self.results.get("package"):
                pkg_match = re.search(r'package=["\']([^"\']+)["\']', str(manifest_data))
                if pkg_match:
                    self.results["package"] = pkg_match.group(1)

            if not self.results.get("version"):
                ver_match = re.search(r'android:versionName=["\']([^"\']+)["\']', str(manifest_data))
                if ver_match:
                    self.results["version"] = ver_match.group(1)

            if not self.results.get("build_code"):
                code_match = re.search(r'android:versionCode=["\']([^"\']+)["\']', str(manifest_data))
                if code_match:
                    self.results["build_code"] = code_match.group(1)

        except Exception as e:
            self.results["errors"].append(f"Manifest error: {e}")

    def _scan_assets_and_droppers(self, z):
        """Scans assets/ and res/raw/ for embedded payloads (hidden DEX/ZIP/APK/DAT files)."""
        try:
            for name in z.namelist():
                low = name.lower()
                if low.startswith(('assets/', 'res/raw/')) and not low.endswith(('.png', '.jpg', '.webp', '.ttf', '.otf', '.mp3', '.ogg')):
                    try:
                        raw = safe_zip_read(z, name, 16 * 1024 * 1024)
                        if raw:
                            # Check for embedded DEX header (dex\n)
                            if raw.startswith(b'dex\n'):
                                try:
                                    for s in DexStrings(raw).get_strings():
                                        self._extract_all_patterns(s)
                                except Exception:
                                    pass

                            # Extract printable strings
                            for s in re.findall(rb'[\x20-\x7E]{6,}', raw):
                                self._extract_all_patterns(s.decode('utf-8', errors='ignore'))
                    except Exception:
                        pass
        except Exception:
            pass

    def _scan_native_libs(self, z):
        """Extracts printable ASCII strings and C2 endpoints from ELF .so shared libraries."""
        try:
            so_files = [n for n in z.namelist() if n.lower().endswith('.so')]
            for name in so_files[:15]:
                try:
                    raw = safe_zip_read(z, name, 12 * 1024 * 1024)
                    if raw:
                        for s_bytes in re.findall(rb'[\x20-\x7E]{6,}', raw):
                            s = s_bytes.decode('utf-8', errors='ignore')
                            self._extract_all_patterns(s)
                except Exception:
                    pass
        except Exception:
            pass

    def _scan_deobfuscate(self, z):
        """Advanced deobfuscation: multi-layer Base64, single-byte XOR, Hex ASCII, URL decode, reversed strings."""
        try:
            targets = [n for n in z.namelist() if n.lower().endswith(
                ('.smali', '.dex', '.json', '.xml', '.properties', '.txt', '.so', '.dat', '.bin'))]
            budget = 48 * 1024 * 1024
            for name in targets[:80]:
                try:
                    info = z.getinfo(name)
                    if info.file_size > 12 * 1024 * 1024 or info.file_size > budget:
                        continue
                    budget -= info.file_size
                    raw = safe_zip_read(z, name, 12 * 1024 * 1024)
                    if not raw:
                        continue

                    # 1. Multi-layer Recursive Base64
                    self._deobfuscate_base64_recursive(raw)

                    # 2. Hex String Decoding
                    self._deobfuscate_hex(raw)

                    # 3. Reversed String Search
                    self._deobfuscate_reversed(raw)

                    # 4. XOR scan with candidate keys if suspicious
                    self._deobfuscate_xor(raw)

                except Exception:
                    continue
        except Exception:
            pass

    def _deobfuscate_base64_recursive(self, raw, depth=0):
        """Recursively decodes nested Base64 blobs up to depth 3."""
        if depth > 2:
            return
        try:
            candidates = re.findall(rb'[A-Za-z0-9+/]{28,}={0,2}', raw)
            for cand in candidates[:500]:
                try:
                    decoded = base64.b64decode(cand, validate=True)
                    text = decoded.decode('utf-8', errors='ignore')
                    if text:
                        self._extract_all_patterns(text)
                        if b'=' in decoded or len(decoded) > 30:
                            self._deobfuscate_base64_recursive(decoded, depth=depth+1)
                except Exception:
                    continue
        except Exception:
            pass

    def _deobfuscate_hex(self, raw):
        """Finds hex-encoded ASCII strings and decodes them."""
        try:
            text = raw.decode('utf-8', errors='ignore')
            hex_candidates = re.findall(r'[0-9a-fA-F]{24,}', text)
            for h in hex_candidates[:100]:
                if len(h) % 2 == 0:
                    try:
                        decoded = bytes.fromhex(h).decode('utf-8', errors='ignore')
                        if decoded and any(k in decoded.lower() for k in ('http', 'firebase', 'aiza', 'bot', 'api')):
                            self._extract_all_patterns(decoded)
                    except Exception:
                        pass
        except Exception:
            pass

    def _deobfuscate_reversed(self, raw):
        """Detects reversed strings (e.g. moc.oiesaberif)."""
        try:
            text = raw.decode('utf-8', errors='ignore')
            if 'moc.oiesaberif' in text or 'ppa.esabataderif' in text or 'yek_ipa' in text:
                reversed_text = text[::-1]
                self._extract_all_patterns(reversed_text)
        except Exception:
            pass

    def _deobfuscate_xor(self, raw):
        """Probes for single-byte XOR obfuscation with common keys."""
        if len(raw) < 16 or len(raw) > 2 * 1024 * 1024:
            return
        common_keys = [0x5A, 0xAA, 0xFF, 0x1F, 0x2A, 0x3C, 0x77, 0x88, 0x99, 0x42, 0x01, 0x10, 0x20, 0x7F]
        for key in common_keys:
            try:
                xored = bytes([b ^ key for b in raw[:4096]])
                if any(s in xored.lower() for s in (b'firebase', b'http', b'aiza', b'discord', b'telegram', b'bot', b'api', b'gate', b'sms')):
                    full_xored = bytes([b ^ key for b in raw])
                    self._extract_all_patterns(full_xored.decode('utf-8', errors='ignore'))
                    break
                elif re.search(rb'\d{8,11}:[a-zA-Z0-9_-]{30}', xored):
                    full_xored = bytes([b ^ key for b in raw])
                    self._extract_all_patterns(full_xored.decode('utf-8', errors='ignore'))
                    break
            except Exception:
                continue

    def _extract_all_patterns(self, text):
        """Master pattern extractor for Firebase, Google APIs, Telegram C2, Webhooks, C2 Gates, and Phone numbers."""
        if not text or not isinstance(text, str):
            return

        if '%' in text:
            try:
                unquoted = urllib.parse.unquote(text)
                if unquoted != text:
                    self._extract_all_patterns(unquoted)
            except Exception:
                pass

        self._extract_firebase(text)
        self._extract_api_keys(text)
        self._extract_telegram_c2(text)
        self._extract_webhooks_and_c2(text)
        self._extract_phone_numbers(text)

    def _extract_firebase(self, text):
        """Extract Firebase RTDB and regional database endpoints."""
        if not text or not isinstance(text, str):
            return
        fb = self.results["firebase"]

        # Normalize escaped slashes often found in JSON / DEX strings
        clean_text = text.replace('\\/', '/')

        # Firebase RTDB Database URLs
        if not fb.get("db_url"):
            for pat in [
                re.compile(r'(?:https?:)?(?://)?([a-zA-Z0-9_-]+-default-rtdb\.(?:[a-z0-9-]+\.)?firebasedatabase\.app)', re.I),
                re.compile(r'(?:https?:)?(?://)?([a-zA-Z0-9_-]+\.(?:[a-z0-9-]+\.)?firebasedatabase\.app)', re.I),
                re.compile(r'(?:https?:)?(?://)?([a-zA-Z0-9_-]+-default-rtdb\.firebaseio\.com)', re.I),
                re.compile(r'(?:https?:)?(?://)?([a-zA-Z0-9_-]+\.firebaseio\.com)', re.I),
                re.compile(r'https?://firestore\.googleapis\.com/v1/projects/([a-zA-Z0-9_-]+)', re.I),
            ]:
                m = pat.search(clean_text)
                if m:
                    val = m.group(1)
                    if 'firestore.googleapis.com' in m.group(0):
                        project_id = val
                        fb["db_url"] = f"https://{project_id}-default-rtdb.firebaseio.com"
                        fb["project_id"] = project_id
                        fb["auth_domain"] = f"{project_id}.firebaseapp.com"
                    else:
                        domain = val
                        fb["db_url"] = f"https://{domain}"
                        project_id = domain.split('.')[0].replace('-default-rtdb', '')
                        fb["project_id"] = project_id
                        fb["auth_domain"] = f"{project_id}.firebaseapp.com"
                    break

        # Sender ID / Project Number
        if not fb.get("sender_id"):
            sender_patterns = [
                r'"project_info".*?"project_number"\s*:\s*"(\d+)"',
                r'gcm_defaultSenderId.*?([0-9]{10,20})',
                r'"sender_id"\s*:\s*"([0-9]{10,20})"',
                r'project_number.*?([0-9]{10,20})'
            ]
            for pattern in sender_patterns:
                match = re.search(pattern, clean_text, re.DOTALL if '"project_info"' in pattern else 0)
                if match:
                    fb["sender_id"] = match.group(1)
                    break

        # Storage bucket
        if not fb.get("storage"):
            storage_patterns = [
                r'([a-zA-Z0-9_-]+)\.appspot\.com',
                r'"storage_bucket"\s*:\s*"([^"]+)"',
                r'storageBucket.*?([a-zA-Z0-9_-]+\.appspot\.com)'
            ]
            for pattern in storage_patterns:
                match = re.search(pattern, clean_text)
                if match:
                    fb["storage"] = match.group(1)
                    break

        if "project_id" in fb and "storage" not in fb:
            fb["storage"] = f"{fb['project_id']}.appspot.com"

    def _extract_api_keys(self, text):
        """Extract Google API Keys and Mobile SDK App IDs."""
        api = self.results["api_credentials"]

        # Google API Key
        if not api.get("google_api_key"):
            api_key_patterns = [
                r'AIza[0-9A-Za-z_-]{30,40}',
                r'"api_key"\s*:\s*"(AIza[0-9A-Za-z_-]{30,40})"',
                r'current_api_key.*?([A-Za-z0-9_-]{35,42})'
            ]
            for pattern in api_key_patterns:
                match = re.search(pattern, text)
                if match:
                    key = match.group(0) if 'AIza' in match.group(0) else match.group(1)
                    if 'AIza' in key:
                        api["google_api_key"] = key
                        break

        # App ID / Mobile SDK
        if not api.get("app_id"):
            app_id_patterns = [
                r'1:\d+:android:[a-f0-9]+',
                r'"mobilesdk_app_id"\s*:\s*"([^"]+)"',
                r'google_app_id.*?([0-9]+:[0-9]+:android:[a-f0-9]+)'
            ]
            for pattern in app_id_patterns:
                match = re.search(pattern, text)
                if match:
                    app_id = match.group(0) if ':' in match.group(0) else match.group(1)
                    api["app_id"] = app_id
                    break

        # OAuth Client IDs
        if not api.get("oauth_clients"):
            oauth_pattern = r'([0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com)'
            oauth_matches = re.findall(oauth_pattern, text)
            if oauth_matches:
                api["oauth_clients"] = list(set(oauth_matches))

        # FCM / GCM Server Key
        if not api.get("fcm_server_key"):
            m_fcm = re.search(r'(?:APA91b|AAAA)[0-9A-Za-z\-_:]{50,}', text)
            if m_fcm:
                api["fcm_server_key"] = m_fcm.group(0)

        # Google Maps API Key
        if not api.get("maps_api_key"):
            m_maps = re.search(r'(?i)(?:maps_api_key|google_maps_key|MAPS_API_KEY)\s*[:="\'\s]+([A-Za-z0-9_-]{20,})', text)
            if m_maps:
                api["maps_api_key"] = m_maps.group(1)

        # Hardcoded Secrets / DB Passwords
        if not api.get("db_secret"):
            m_sec = re.search(r'(?i)(?:admin_pass|secret_key|api_secret|db_pass)\s*[:="\'\s]+([A-Za-z0-9@#$%^&*!_-]{4,})', text)
            if m_sec:
                api["db_secret"] = m_sec.group(1)

    def _extract_telegram_c2(self, text):
        """Extract Telegram C2 Bot Tokens and Chat IDs."""
        tg = self.results["telegram_c2"]
        if not tg.get("bot_token"):
            m = re.search(r'\b(\d{8,11}:[a-zA-Z0-9_-]{35})\b', text)
            if m:
                tok = m.group(1)
                if tok != BOT_TOKEN:
                    tg["bot_token"] = tok

        if not tg.get("chat_id"):
            m = re.search(r'(?:^|[^\w])(-100\d{8,13})\b', text)
            if m:
                cid = m.group(1)
                if cid != str(LOG_CHANNEL):
                    tg["chat_id"] = cid

    def _extract_webhooks_and_c2(self, text):
        """Extract Discord, Slack, and REST C2 URLs."""
        for m in re.finditer(r'https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+', text):
            u = m.group(0)
            if u not in self.results["webhooks"]:
                self.results["webhooks"].append(u)

        for m in re.finditer(r'https://hooks\.slack\.com/services/T[a-zA-Z0-9_]+/B[a-zA-Z0-9_]+/[a-zA-Z0-9_]+', text):
            u = m.group(0)
            if u not in self.results["webhooks"]:
                self.results["webhooks"].append(u)

        for m in re.finditer(r'https?://(?:[a-zA-Z0-9.-]+|(?:\d{1,3}\.){3}\d{1,3})(?::\d+)?/(?:api/|gate|panel|upload|bot|sms|receiver|forward)[a-zA-Z0-9_./-]*', text, re.I):
            u = m.group(0)
            if not any(ign in u.lower() for ign in ["google", "github", "firebase", "android", "schema.org", "w3.org", "discord", "telegram", "t.me"]):
                if u not in self.results["c2_endpoints"] and len(self.results["c2_endpoints"]) < 10:
                    self.results["c2_endpoints"].append(u)

    def _extract_phone_numbers(self, text):
        """Extract hardcoded SMS forwarding target phone numbers."""
        if any(k in text.lower() for k in ("sendtextmessage", "forward_to", "admin_number", "target_number", "sms_receiver", "phone_number")):
            for m in re.finditer(r'(?:\+91|91)?([6-9]\d{9})\b', text):
                num = m.group(0)
                if num not in self.results["forward_phones"] and len(self.results["forward_phones"]) < 6:
                    self.results["forward_phones"].append(num)

    def _extract_google_services(self, data):
        """Parse google-services.json structurally for exact values."""
        try:
            obj = json.loads(data)
        except Exception:
            return

        fb = self.results["firebase"]
        project_info = obj.get("project_info", {})

        furl = project_info.get("firebase_url")
        if furl and not fb.get("db_url"):
            fb["db_url"] = furl

        if not fb.get("project_id"):
            pid = project_info.get("project_id")
            if pid:
                fb["project_id"] = pid
                if not fb.get("db_url"):
                    fb["db_url"] = f"https://{pid}-default-rtdb.firebaseio.com"
                fb["auth_domain"] = f"{pid}.firebaseapp.com"

        if not fb.get("sender_id"):
            pnum = project_info.get("project_number")
            if pnum:
                fb["sender_id"] = str(pnum)

        if not fb.get("storage"):
            bucket = project_info.get("storage_bucket")
            if bucket:
                fb["storage"] = bucket

        api = self.results["api_credentials"]
        fopts = obj.get("firebase_options", {}).get("client", {})
        if not api.get("google_api_key"):
            ak = fopts.get("api_key")
            if ak and str(ak).startswith("AIza"):
                api["google_api_key"] = str(ak)

        if not api.get("app_id"):
            aid = fopts.get("mobilesdk_app_id")
            if not aid:
                clients = obj.get("client", []) or []
                if clients:
                    aid = clients[0].get("client_info", {}).get("mobilesdk_app_id")
            if aid:
                api["app_id"] = aid

        if not api.get("oauth_clients"):
            oauth = set()
            for cli in obj.get("client", []) or []:
                for o in cli.get("oauth_client", []) or []:
                    cid = o.get("client_id")
                    if cid and '.' in cid:
                        oauth.add(cid)
            if oauth:
                api["oauth_clients"] = list(oauth)

        text = data.decode('utf-8', errors='ignore')
        self._extract_all_patterns(text)

    def _detect_packer(self, z):
        """Detect known packers, protectors, and heavy obfuscation."""
        packers = []
        try:
            files = z.namelist()

            signatures = [
                ('libjiagu', "Jiagu"),
                ('libmobisec', "Mobisec"),
                ('libshell', "360 Jiagu"),
                ('libbaiduprotect', "Baidu Protect"),
                ('libtup', "Tencent TUP"),
                ('libedog', "Bangcle"),
                ('libchaosvmp', "Naga/ChaosVMP"),
                ('libsecexe', "SecNeo"),
                ('libsecneo', "SecNeo"),
                ('libprotect', "Custom Protect"),
                ('np.protect', "NP Protect / NP Manager"),
                ('libnp', "NP Protect"),
                ('mtbin', "MT Manager"),
                ('libmtprotect', "MT Protect"),
                ('dexprotector', "DexProtector"),
                ('allatori', "Allatori Obfuscator"),
                ('promon', "Promon SHIELD"),
                ('medusa', "Medusa Protector"),
                ('appguard', "AppGuard"),
            ]

            for sig, name in signatures:
                if any(sig in f.lower() for f in files):
                    packers.append(name)

            dex_files = [f for f in files if f.endswith('.dex')]
            if len(dex_files) > 5:
                packers.append("Multi-Dex (Heavy Split)")

            native_libs = [f for f in files if f.endswith('.so')]
            if len(native_libs) > 20:
                packers.append("Heavy Native Libs")

        except Exception as e:
            self.results["errors"].append(f"Packer detection error: {e}")

        self.results["packer"] = ", ".join(packers) if packers else "None detected"

    def _add_corpus(self, corpus, items):
        room = MAX_CORPUS_STRINGS - len(corpus)
        if room > 0:
            corpus.extend(items[:room])


# ==================== BOT ====================
# In-memory session — no .session file needed on Replit/Railway.
# Optional: set SESSION env var to a StringSession to persist logins across restarts.
client = TelegramClient(StringSession(os.environ.get("SESSION", "")), API_ID, API_HASH)

async def log_to_channel(text):
    """Send log to channel"""
    try:
        await client.send_message(LOG_CHANNEL, text, link_preview=False)
    except Exception:
        pass

async def log_to_owner(text):
    """Send notification to the owner's DM."""
    try:
        await client.send_message(OWNER_ID, text, link_preview=False)
    except Exception:
        pass

async def _edit_progress(msg, text, last_edit):
    """Edit a progress message, throttled to avoid rate-limit floods."""
    now = time.monotonic()
    if now - last_edit >= PROGRESS_EDIT_INTERVAL:
        try:
            await msg.edit(text)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 0.5)
        except Exception:
            pass
        return now
    return last_edit

async def _safe_delete(msg):
    try:
        await msg.delete()
    except Exception:
        pass

async def _retry(fn, *args, **kwargs):
    """Run a send/await call, retrying once after any flood wait."""
    for _ in range(3):
        try:
            return await fn(*args, **kwargs)
        except FloodWaitError as e:
            print(f"[{BRAND_NAME}] Flood wait: {e.seconds}s")
            await asyncio.sleep(e.seconds + 1)
    return await fn(*args, **kwargs)

def avg_scan_time(uid):
    """Average time per scan for a user, falling back to global average."""
    history = SCAN_HISTORY.get(uid, [])
    times = [h["scan_time"] for h in history if h.get("scan_time")]
    if times:
        return sum(times) / len(times)
    if BOT_STATS["total_scans"] and BOT_STATS["total_scan_time"]:
        return BOT_STATS["total_scan_time"] / BOT_STATS["total_scans"]
    return 12.0  # conservative default before we have real data


def estimate_eta(uid, pending):
    """Estimated seconds to finish the remaining queued APKs."""
    return pending * avg_scan_time(uid)


def format_bytes(size):
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def _hash_file(path):
    """Quick sha1 of a file — used as the scan-cache key."""
    h = hashlib.sha1()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()

def probe_firebase_database(db_url: str, auth_key: str = None, timeout: float = 2.5) -> dict:
    """Probes a Firebase Realtime Database for online/offline/total devices and access status."""
    if not db_url or "firebase" not in db_url:
        return {}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # Canonical root host extraction & auto-extract auth param if embedded in URL
    parsed = urllib.parse.urlparse(db_url if "://" in db_url else f"https://{db_url}")
    host = parsed.netloc.lower() or parsed.path.lower().split("/")[0]
    clean_url = f"https://{host}"

    if not auth_key and parsed.query:
        try:
            qs = urllib.parse.parse_qs(parsed.query)
            if "auth" in qs:
                auth_key = qs["auth"][0]
        except Exception:
            pass

    results = {
        "status": "Unknown",
        "accessible": False,
        "online": 0,
        "offline": 0,
        "total": 0,
        "nodes": []
    }

    def _get(path: str, use_auth: bool = False):
        clean_path = path.lstrip("/")
        url = f"{clean_url}/{clean_path}"
        if use_auth and auth_key:
            sep = "&" if "?" in url else "?"
            url += f"{sep}auth={auth_key}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)

    def _eval_devices(data_dict):
        if not isinstance(data_dict, dict):
            return 0, 0, 0
        now = time.time()
        online = 0
        offline = 0
        for dev_id, v in data_dict.items():
            is_on = False
            if isinstance(v, dict):
                st = v.get("status") or v.get("isOnline") or v.get("online") or v.get("state") or v.get("connected")
                if st is True or st == 1 or str(st).lower() in ("online", "true", "active", "connected", "1"):
                    is_on = True
                else:
                    for ts_field in ("timestamp", "last_seen", "lastSeen", "lastOnline", "lastMessageTime", "time"):
                        val = v.get(ts_field)
                        if isinstance(val, dict):
                            val = val.get("timestamp") or val.get("time")
                        if val:
                            try:
                                t_float = float(val)
                                if t_float > 1e12:
                                    t_float /= 1000.0
                                if 0 < (now - t_float) < 900:  # 15 minutes
                                    is_on = True
                                    break
                            except Exception:
                                pass
            if is_on:
                online += 1
            else:
                offline += 1
        return online, offline, len(data_dict)

    auth_options = [False, True] if auth_key else [False]

    # 1. Probe root shallow first (fastest single-request check for completely open databases)
    for use_auth in auth_options:
        try:
            with _get(".json?shallow=true", use_auth=use_auth) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8", errors="ignore")
                    if raw and raw != "null":
                        root_keys = json.loads(raw)
                        if isinstance(root_keys, dict) and root_keys:
                            results["accessible"] = True
                            results["status"] = "🟢 Open (Accessible)" if not use_auth else "🔑 Auth Verified"
                            results["nodes"] = list(root_keys.keys())[:8]

                            # Check if known device endpoints exist at root
                            dev_node = next((k for k in ["clients", "devices", "victim", "victims", "users", "bots", "phones", "all_pas", "data"] if k in root_keys), None)
                            if dev_node:
                                try:
                                    with _get(f"{dev_node}.json?shallow=true", use_auth=use_auth) as dev_resp:
                                        if dev_resp.status == 200:
                                            dev_raw = dev_resp.read().decode("utf-8", errors="ignore")
                                            if dev_raw and dev_raw != "null":
                                                dev_dict = json.loads(dev_raw)
                                                if isinstance(dev_dict, dict):
                                                    results["total"] = len(dev_dict)
                                                    results["offline"] = len(dev_dict)
                                                    if len(dev_dict) <= 15:
                                                        try:
                                                            with _get(f"{dev_node}.json", use_auth=use_auth) as full_resp:
                                                                full_data = json.loads(full_resp.read(262144).decode("utf-8", errors="ignore"))
                                                                if isinstance(full_data, dict):
                                                                    on, off, tot = _eval_devices(full_data)
                                                                    results["online"] = on
                                                                    results["offline"] = off
                                                                    results["total"] = tot
                                                        except Exception:
                                                            pass
                                except Exception:
                                    pass
                            elif any(re.match(r'^[a-fA-F0-9]{12,36}$', k) for k in list(root_keys.keys())[:5]):
                                results["total"] = len(root_keys)
                                results["offline"] = len(root_keys)
                            return results
                        elif root_keys == {}:
                            results["accessible"] = True
                            results["status"] = "🟢 Open (Empty Database)" if not use_auth else "🔑 Auth Verified (Empty)"
                            return results
        except urllib.error.HTTPError as he:
            if he.code == 402:
                results["status"] = "⚠️ Quota Exceeded (402 Payment Required)"
                return results
            elif he.code == 423:
                results["status"] = "🔴 Deactivated / Suspended (423 Locked)"
                return results
            elif he.code in (401, 403):
                results["status"] = "🔒 Protected (Auth Required)"
            elif he.code != 404:
                results["status"] = f"⚪ HTTP {he.code}"
        except urllib.error.URLError:
            results["status"] = "🔴 Unreachable (Host Not Found)"
            return results
        except Exception:
            pass

    # 2. Probe granular endpoints (Firebase rules often protect root but allow read on specific child endpoints)
    custom_path = parsed.path.strip("/").rstrip(".json")
    device_endpoints = ["clients", "devices", "victim", "victims", "users", "data", "online", "bots", "phones", "all_pas"]
    if custom_path and custom_path not in device_endpoints:
        device_endpoints.insert(0, custom_path)

    for ep in device_endpoints:
        for use_auth in auth_options:
            try:
                with _get(f"{ep}.json?shallow=true", use_auth=use_auth) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8", errors="ignore")
                        if raw and raw != "null":
                            keys_dict = json.loads(raw)
                            if isinstance(keys_dict, dict) and keys_dict:
                                results["accessible"] = True
                                results["status"] = "🟢 Open (Accessible)" if not use_auth else "🔑 Auth Verified"
                                results["total"] = len(keys_dict)
                                results["offline"] = len(keys_dict)
                                results["nodes"] = [ep]
                                if len(keys_dict) <= 15:
                                    try:
                                        with _get(f"{ep}.json", use_auth=use_auth) as full_resp:
                                            raw_bytes = full_resp.read(262144)
                                            full_data = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
                                            if isinstance(full_data, dict):
                                                on, off, tot = _eval_devices(full_data)
                                                results["online"] = on
                                                results["offline"] = off
                                                results["total"] = tot
                                    except Exception:
                                        pass
                                return results
                            elif isinstance(keys_dict, list) and keys_dict:
                                results["accessible"] = True
                                results["status"] = "🟢 Open (Accessible)" if not use_auth else "🔑 Auth Verified"
                                results["total"] = len(keys_dict)
                                results["nodes"] = [ep]
                                return results
            except urllib.error.HTTPError as he:
                if he.code == 402:
                    results["status"] = "⚠️ Quota Exceeded (402 Payment Required)"
                    return results
                elif he.code == 423:
                    results["status"] = "🔴 Deactivated / Suspended (423 Locked)"
                    return results
                elif he.code in (401, 403):
                    if results["status"] == "Unknown":
                        results["status"] = "🔒 Protected (Auth Required)"
                    continue
                elif he.code == 404:
                    continue
                else:
                    if results["status"] == "Unknown":
                        results["status"] = f"⚪ HTTP {he.code}"
                    continue
            except Exception:
                pass

    if results["status"] == "Unknown":
        results["status"] = "⚪ Inactive / Unreachable"
    return results

def format_firebase_probe_report(db_url, dev_stats):
    """Format a standalone live database check report."""
    e = EMOJIS
    lines = [
        f"🔍 **FIREBASE LIVE DIAGNOSTIC**",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"🌐 **Target URL:** `{db_url}`",
        f"🛡️ **Status:** {dev_stats.get('status', 'Unknown')}",
        ""
    ]
    if dev_stats.get("accessible"):
        lines.append("📊 **Live Device Stats:**")
        if dev_stats.get("total", 0) > 0:
            lines.append(f"🟢 Online Devices:  `{dev_stats.get('online', 0)}`")
            lines.append(f"🔴 Offline Devices: `{dev_stats.get('offline', 0)}`")
            lines.append(f"📱 Total Devices:   `{dev_stats.get('total', 0)}`")
        else:
            lines.append("📱 Total Devices:   `0 devices / Inactive`")

        if dev_stats.get("nodes"):
            nodes_str = ", ".join(f"`/{n}`" for n in dev_stats["nodes"])
            lines.append(f"📁 Root Nodes: {nodes_str}")
        lines.append("")

    lines.append(f"━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"{e['zap']} Powered by {BRAND_NAME}")
    return "\n".join(lines)


def get_scan_text(results, file_size="Unknown"):
    """Format scan results cleanly into Firebase link, credentials, and device count."""
    e = EMOJIS
    fb = results.get("firebase", {})
    api = results.get("api_credentials", {})
    tg = results.get("telegram_c2", {})
    dev_stats = results.get("device_stats", {})

    lines = [
        f"{e['fire']} **FIREBASE EXTRACTION REPORT**",
        "",
        f"📦 **APK:** `{results.get('filename', 'Unknown')}`",
        f"📏 **Size:** `{file_size}`",
    ]

    if results.get("app_name"):
        lines.append(f"📱 **App Name:** `{results['app_name']}`")
    if results.get("package"):
        ver_str = f" v{results.get('version')}" if results.get('version') else ""
        lines.append(f"🏷️ **Package:** `{results.get('package')}{ver_str}`")

    packer = results.get("packer")
    if packer:
        packer_icon = "🛡️" if packer == "None detected" else "⚠️"
        lines.append(f"{packer_icon} **Packer / Obfuscator:** `{packer}`")

    lines.append("")
    lines.append(f"🌐 **DB URL:** `{fb.get('db_url') or '❌ Not found'}`")

    if fb.get("project_id"):
        lines.append(f"🆔 **Project ID:** `{fb['project_id']}`")
    if fb.get("storage"):
        lines.append(f"🪣 **Storage Bucket:** `{fb['storage']}`")
    if fb.get("sender_id"):
        lines.append(f"📧 **Sender ID:** `{fb['sender_id']}`")

    # API Credentials & Keys
    if api.get("google_api_key"):
        lines.append(f"🔑 **Google API Key:** `{api['google_api_key']}`")
    if api.get("app_id"):
        lines.append(f"📱 **Mobile App ID:** `{api['app_id']}`")
    if api.get("fcm_server_key"):
        lines.append(f"📲 **FCM Server Key:** `{api['fcm_server_key']}`")
    if api.get("maps_api_key"):
        lines.append(f"🗺️ **Maps API Key:** `{api['maps_api_key']}`")
    if api.get("db_secret"):
        lines.append(f"🔐 **Hardcoded Secret:** `{api['db_secret']}`")
    if api.get("oauth_clients"):
        lines.append(f"🔑 **OAuth Client:** `{', '.join(api['oauth_clients'][:2])}`")

    # Threat Intelligence / RAT C2
    threat_lines = []
    if tg.get("bot_token"):
        threat_lines.append(f"🤖 **C2 Telegram Bot:** `{tg['bot_token']}`")
    if tg.get("chat_id"):
        threat_lines.append(f"💬 **C2 Chat ID:** `{tg['chat_id']}`")
    if results.get("c2_endpoints"):
        c2_str = ", ".join(f"`{u}`" for u in results["c2_endpoints"][:2])
        threat_lines.append(f"🌐 **C2 Gateways:** {c2_str}")
    if results.get("webhooks"):
        wb_str = ", ".join(f"`{w}`" for w in results["webhooks"][:2])
        threat_lines.append(f"🔗 **Webhooks:** {wb_str}")
    if results.get("forward_phones"):
        ph_str = ", ".join(f"`{p}`" for p in results["forward_phones"][:2])
        threat_lines.append(f"📞 **SMS Intercept:** {ph_str}")

    if threat_lines:
        lines.append("")
        lines.append("🚨 **Threat Intelligence & C2:**")
        lines.extend(threat_lines)

    lines.append("")

    # Live Device Statistics
    if dev_stats:
        lines.append(f"📊 **Device Statistics**")
        if dev_stats.get("accessible") and dev_stats.get("total", 0) > 0:
            lines.append(f"🟢 Online:  `{dev_stats.get('online', 0)}`")
            lines.append(f"🔴 Offline: `{dev_stats.get('offline', 0)}`")
            lines.append(f"📱 Total:   `{dev_stats.get('total', 0)}`")
        elif dev_stats.get("accessible"):
            lines.append(f"📱 Total:   `0 devices`")

        lines.append(f"🛡️ DB Access: {dev_stats.get('status', 'Unknown')}")
        if dev_stats.get("nodes"):
            nodes_str = ", ".join(f"`/{n}`" for n in dev_stats["nodes"])
            lines.append(f"📁 Root Nodes: {nodes_str}")
        lines.append("")

    lines.append(f"━" * 20)
    lines.append(f"{e['zap']} Powered by {BRAND_NAME} {e['rocket']}")

    return "\n".join(lines)

def render_progress_bar(pct: int, status_text: str, filename: str, queue_text: str = "") -> str:
    """Renders a dynamic visual progress bar and status for scan processing."""
    pct = max(0, min(100, int(pct)))
    filled = int(pct / 10)
    bar = f"[{'█' * filled}{'░' * (10 - filled)}] {pct}%"
    return (
        f"⚙️ <b>{BRAND_NAME} SCAN ENGINE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>File:</b> <code>{filename}</code>{queue_text}\n"
        f"<code>{bar}</code>\n\n"
        f"⚡ <i>{status_text}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

# ==================== HANDLERS ====================
@client.on(events.NewMessage(pattern=r'(?i)^/start(\s+[\s\S]+)?$'))
async def start_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    if not uid:
        return

    user = await event.get_sender()
    first_name = user.first_name if (user and hasattr(user, 'first_name') and user.first_name) else 'User'

    if not await check_fsub(uid):
        await event.reply(get_fsub_message(first_name), buttons=get_fsub_buttons(), link_preview=False)
        return

    # Update stats & save user
    save_user(uid)
    if USER_STATS[uid]["first_seen"] is None:
        USER_STATS[uid]["first_seen"] = datetime.now()
    USER_STATS[uid]["last_seen"] = datetime.now()

    e = EMOJIS

    welcome_text = f"""{e['zap']} **{'━'*10}** {e['zap']}
{e['fire']} **FIREBASE EXTRACTOR BOT** {e['fire']}
{e['zap']} **{'━'*10}** {e['zap']}

👋 Hey ❖ **{first_name}** ❖! Welcome to the most advanced Firebase extractor on Telegram.

◆ **{'━'*10}** ◆

**What I Extract from APKs:**
{e['fire']} Firebase Database URL & Live Status
{e['key']} Google API Key & App ID
{e['bucket']} FCM Server Keys & Google Maps Key
{e['shield']} Hardcoded DB Passwords & Secrets
{e['shield']} Telegram C2 Bots & Malicious Gateways
{e['package']} Package name & version
{e['bucket']} Project ID & Storage Bucket
{e['shield']} Packer detection

**How to Scan:**
Just send me any `.apk` file (supports multi-scan concurrently!).
{e['check']} Completely free
{e['check']} Multi-scan queue (Parallel analysis)
{e['check']} Direct URL checking supported

`/help`   — Commands
`/firebase <url>` — Check a Firebase URL directly
`/history` — Your scan history
`/stats`  — Bot statistics
`/myid`   — Your profile

◆ **{'━'*10}** ◆"""

    if uid in ADMIN_IDS:
        ensure_admin_menu(uid)
        welcome_text += f"""

━━━━━━━━━━━━━━━━━━━━
👑 **ADMIN ACCESS GRANTED:**
• `/admin` / `/panel` — Interactive Admin Control Suite
• `/maint` — Toggle Maintenance Mode
• `/broadcast <msg>` — Send Broadcast Announcement
• `/ban <user_id>` — Ban a user ID
• `/unban <user_id>` — Unban a user ID
• `/banned` — List all banned users
━━━━━━━━━━━━━━━━━━━━"""
        buttons = [
            [styled_button("⚡ 👑 ADMIN CONTROL SUITE 👑 ⚡", b"admin_refresh", color="danger")],
            [styled_button(f"{e['folder']} My Scans", b"history", color="primary"), styled_button(f"{e['chart']} Statistics", b"stats", color="success")],
            [styled_button(f"{e['link']} Support Community", url=f"https://t.me/{OWNER_USERNAME.replace('@', '')}", color="primary")]
        ]
    else:
        buttons = [
            [styled_button(f"{e['folder']} My Scans", b"history", color="primary"), styled_button(f"{e['chart']} Statistics", b"stats", color="success")],
            [styled_button(f"{e['link']} Support Community", url=f"https://t.me/{OWNER_USERNAME.replace('@', '')}", color="primary")]
        ]

    await event.reply(welcome_text, buttons=buttons)

    # Log
    await log_to_channel(
        f"{e['zap']} **New User Started Bot**\n"
        f"👤 Name: [{first_name}](tg://user?id={uid})\n"
        f"🆔 ID: `{uid}`\n"
        f"📅 Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )

@client.on(events.NewMessage(pattern=r'(?i)^/help'))
async def help_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id

    if not await check_fsub(uid):
        user = await event.get_sender()
        first_name = user.first_name if (user and hasattr(user, 'first_name') and user.first_name) else 'User'
        await event.reply(get_fsub_message(first_name), buttons=get_fsub_buttons(), link_preview=False)
        return

    e = EMOJIS
    help_text = f"""{e['info']} **BOT COMMANDS**

**User Commands:**
`/start` — Start the bot
`/help` — Show this message
`/firebase <url>` — Live probe any Firebase DB URL
`/check <url>` — Alias for /firebase
`/history` — View your scan history
`/stats` — Bot usage statistics
`/myid` — Get your Telegram ID

**How to use:**
1. Send any `.apk` file (can send multiple APKs simultaneously!)
2. Wait for lightning-fast parallel processing
3. Get comprehensive credentials & live device report

**Extracted Data:**
• Firebase Realtime Database URL
• Firebase Project ID & Auth Domain
• GCM / FCM Server Keys
• Google Maps API Key
• Hardcoded DB Passwords & Secrets
• Google API Key & Mobile App ID
• Telegram C2 RAT Bot Tokens & Webhooks
• Package information & Packer detection

◆ **{'━'*10}** ◆
{e['zap']} Powered by {BRAND_NAME}"""

    if uid in ADMIN_IDS:
        ensure_admin_menu(uid)
        help_text += f"""

━━━━━━━━━━━━━━━━━━━━
👑 **ADMIN EXCLUSIVE COMMANDS:**
• `/admin` or `/panel` — Open Interactive Admin Dashboard
• `/maint` — Toggle Maintenance Mode
• `/broadcast <msg>` — Send Broadcast to all users
• `/ban <user_id>` — Ban a user
• `/unban <user_id>` — Unban a user
• `/banned` — Show all banned users
━━━━━━━━━━━━━━━━━━━━"""
        buttons = [
            [styled_button("⚡ 👑 OPEN ADMIN SUITE 👑 ⚡", b"admin_refresh", color="danger")],
            [styled_button(f"{e['folder']} My Scans", b"history", color="primary"), styled_button(f"{e['chart']} Statistics", b"stats", color="success")],
            [styled_button(f"{e['link']} Support Community", url=f"https://t.me/{OWNER_USERNAME.replace('@', '')}", color="primary")]
        ]
    else:
        buttons = [
            [styled_button(f"{e['folder']} My Scans", b"history", color="primary"), styled_button(f"{e['chart']} Statistics", b"stats", color="success")],
            [styled_button(f"{e['link']} Support Community", url=f"https://t.me/{OWNER_USERNAME.replace('@', '')}", color="primary")]
        ]

    await event.reply(help_text, buttons=buttons)

# Force Subscribe Verification Callback
@client.on(events.CallbackQuery(pattern=b"check_fsub_btn"))
async def check_fsub_callback(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    joined = await check_fsub(uid)
    if joined:
        await event.answer("✅ Verification successful! Access granted.", alert=True)
        try:
            await event.delete()
        except Exception:
            pass
        user = await event.get_sender()
        first_name = getattr(user, 'first_name', 'User') or 'User'
        e = EMOJIS
        welcome_text = f"🎉 **Welcome {first_name}!**\n\nYou now have full access to **{BRAND_NAME} Firebase Extractor**.\n\nSend any `.apk` file to scan, or use `/firebase <url>` to check a database directly."
        buttons = [
            [styled_button(f"{e['folder']} History", b"history", color="primary"), styled_button(f"{e['chart']} Stats", b"stats", color="success")],
            [styled_button(f"{e['link']} Support", url=f"https://t.me/{OWNER_USERNAME.replace('@', '')}", color="primary")]
        ]
        await client.send_message(event.chat_id, welcome_text, buttons=buttons)
    else:
        await event.answer(f"❌ You haven't joined yet! Please join {FSUB_CHANNEL} and tap again.", alert=True)

# Direct Firebase Database Checker Command
@client.on(events.NewMessage(pattern=r'^/(firebase|check)(\s+[\s\S]+)?$'))
async def firebase_check_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    if not uid:
        return
    if not await check_fsub(uid):
        user = await event.get_sender()
        fname = getattr(user, 'first_name', 'User') or 'User'
        await event.reply(get_fsub_message(fname), buttons=get_fsub_buttons(), link_preview=False)
        return

    e = EMOJIS
    raw_arg = event.pattern_match.group(2)
    if not raw_arg or not raw_arg.strip():
        await event.reply(
            f"{e['search']} **FIREBASE DATABASE CHECKER**\n\n"
            f"Test whether any Firebase Realtime Database is public, open, or locked.\n\n"
            f"**Usage:** `/firebase <database_url>`\n\n"
            f"**Examples:**\n"
            f"• `/firebase https://myproject-default-rtdb.firebaseio.com`\n"
            f"• `/check https://myproject.firebaseio.com`"
        )
        return

    target_url = raw_arg.strip().split()[0].strip("\"'`<>[]()")
    if not target_url.startswith(("http://", "https://")):
        target_url = f"https://{target_url}"

    status_msg = await event.reply(f"{e['chart']} Checking database `{target_url}` live...")

    parts = raw_arg.strip().split()
    auth_key = parts[1].strip("\"'`<>[]()") if len(parts) > 1 else None

    dev_stats = await asyncio.to_thread(probe_firebase_database, target_url, auth_key)
    report = format_firebase_probe_report(target_url, dev_stats)
    await _retry(status_msg.edit, report, link_preview=False)

# Inline Button Callback for Live Database Check
@client.on(events.CallbackQuery(pattern=r'^check_fb:(.+)'))
async def check_fb_callback_handler(event):
    if not await telecore_guard(event):
        return
    raw_data = event.pattern_match.group(1).decode('utf-8', errors='ignore').strip()
    await event.answer("🔍 Checking database live...", alert=False)
    target_url = URL_CACHE.get(raw_data) or raw_data
    target_url = target_url.strip("\"'`<>[]()")
    if not target_url.startswith(("http://", "https://")):
        target_url = f"https://{target_url}"

    dev_stats = await asyncio.to_thread(probe_firebase_database, target_url)
    report = format_firebase_probe_report(target_url, dev_stats)
    await event.reply(report, link_preview=False)

@client.on(events.NewMessage(pattern=r'(?i)^/myid$'))
async def myid_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    user = await event.get_sender()
    e = EMOJIS
    first_name = user.first_name if (user and hasattr(user, 'first_name') and user.first_name) else 'N/A'
    username = f"@{user.username}" if (user and hasattr(user, 'username') and user.username) else 'N/A'
    is_admin = uid in ADMIN_IDS
    role_str = "👑 Administrator / Owner" if is_admin else "👤 Standard User"
    text = f"""{e['id_card']} **YOUR PROFILE**

👤 Name: {first_name}
🆔 User ID: `{uid}`
📛 Username: {username}
🎖 Role: `{role_str}`

◆ **{'━'*10}** ◆"""
    buttons = None
    if is_admin:
        ensure_admin_menu(uid)
        buttons = [[styled_button("⚡ Admin Control Panel", b"admin_refresh", color="danger")]]
    await event.reply(text, buttons=buttons)

@client.on(events.NewMessage(pattern=r'(?i)^/stats$'))
async def stats_handler(event):
    if not await telecore_guard(event):
        return
    e = EMOJIS
    uptime = datetime.now() - BOT_STATS["start_time"]
    days = uptime.days
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(rem, 60)

    avg = (BOT_STATS["total_scan_time"] / BOT_STATS["total_scans"]) if BOT_STATS["total_scans"] else 0
    text = f"""{e['chart']} **BOT STATISTICS**

📊 Total Scans: `{BOT_STATS['total_scans']}`
👥 Total Users: `{len(BOT_STATS['total_users'])}`
{e['timer']} Avg Scan Time: `{avg:.2f}s`
⏱ Uptime: `{days}d {hours}h {minutes}m`

◆ **{'━'*10}** ◆
{e['zap']} {BRAND_NAME}"""

    await event.reply(text)

@client.on(events.NewMessage(pattern=r'(?i)^/history$'))
async def history_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    e = EMOJIS
    history = SCAN_HISTORY.get(uid, [])

    if not history:
        await event.reply(f"{e['folder']} **No scan history found.**\n\nSend an APK to start scanning!")
        return

    text = f"{e['folder']} **YOUR SCAN HISTORY**\n\n"
    for i, item in enumerate(history[-10:], 1):
        text += f"{i}. `{item['filename']}` — {item['time']}\n"

    text += f"\n◆ **{'━'*10}** ◆"
    await event.reply(text)

@client.on(events.CallbackQuery)
async def callback_handler(event):
    if not await telecore_guard(event):
        return
    data = event.data.decode()
    uid = event.sender_id
    e = EMOJIS

    if data == "history":
        history = SCAN_HISTORY.get(uid, [])
        back_btn = [[styled_button("🔙 Main Menu", b"main_menu", color="danger")]]
        if not history:
            await event.edit(f"{e['folder']} **No scan history found.**\n\nSend an APK to start scanning!", buttons=back_btn)
        else:
            text = f"{e['folder']} **YOUR SCAN HISTORY**\n\n"
            for i, item in enumerate(history[-10:], 1):
                text += f"{i}. `{item['filename']}` — {item['time']}\n"
            text += f"\n◆ **{'━'*10}** ◆"
            await event.edit(text, buttons=back_btn)

    elif data == "stats":
        uptime = datetime.now() - BOT_STATS["start_time"]
        days = uptime.days
        hours, rem = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        avg = (BOT_STATS["total_scan_time"] / BOT_STATS["total_scans"]) if BOT_STATS["total_scans"] else 0
        text = f"""{e['chart']} **BOT STATISTICS**

📊 Total Scans: `{BOT_STATS['total_scans']}`
👥 Total Users: `{len(BOT_STATS['total_users'])}`
{e['timer']} Avg Scan Time: `{avg:.2f}s`
⏱ Uptime: `{days}d {hours}h {minutes}m`

◆ **{'━'*10}** ◆
{e['zap']} {BRAND_NAME}"""
        back_btn = [[styled_button("🔙 Main Menu", b"main_menu", color="danger")]]
        await event.edit(text, buttons=back_btn)

    elif data == "scan_again":
        back_btn = [[styled_button("🔙 Main Menu", b"main_menu", color="danger")]]
        await event.edit(f"{e['fire']} **Send an APK to Start Scanning!**", buttons=back_btn)

    elif data == "main_menu":
        user = await event.get_sender()
        first_name = getattr(user, 'first_name', 'User') or 'User'
        welcome_text = f"""{e['fire']} **FIREBASE EXTRACTOR ENGINE**
━━━━━━━━━━━━━━━━━━━━
👋 Hello, [{first_name}](tg://user?id={uid})!

Send me any **APK file** to instantly extract:
• Firebase Database URLs & Probes
• API Keys, Tokens & Auth Domains
• Server Keys & Push Credentials
• Live Node & Device Statistics

◆ **{'━'*10}** ◆"""
        if uid in ADMIN_IDS:
            ensure_admin_menu(uid)
            welcome_text += f"""

━━━━━━━━━━━━━━━━━━━━
👑 **ADMIN ACCESS GRANTED:**
• `/admin` / `/panel` — Interactive Admin Control Suite
• `/maint` — Toggle Maintenance Mode
• `/broadcast <msg>` — Send Broadcast Announcement
• `/ban <user_id>` — Ban a user ID
• `/unban <user_id>` — Unban a user ID
• `/banned` — List all banned users
━━━━━━━━━━━━━━━━━━━━"""
            buttons = [
                [styled_button("⚡ 👑 ADMIN CONTROL SUITE 👑 ⚡", b"admin_refresh", color="danger")],
                [styled_button(f"{e['folder']} My Scans", b"history", color="primary"), styled_button(f"{e['chart']} Statistics", b"stats", color="success")],
                [styled_button(f"{e['link']} Support Community", url=f"https://t.me/{OWNER_USERNAME.replace('@', '')}", color="primary")]
            ]
        else:
            buttons = [
                [styled_button(f"{e['folder']} My Scans", b"history", color="primary"), styled_button(f"{e['chart']} Statistics", b"stats", color="success")],
                [styled_button(f"{e['link']} Support Community", url=f"https://t.me/{OWNER_USERNAME.replace('@', '')}", color="primary")]
            ]
        await event.edit(welcome_text, buttons=buttons)

    elif data in ("admin_refresh", "admin_panel"):
        if uid not in ADMIN_IDS:
            await event.answer("❌ Admin access required.", alert=True)
            return
        panel_text, buttons = build_admin_panel()
        try:
            await event.edit(panel_text, buttons=buttons)
        except Exception:
            await event.reply(panel_text, buttons=buttons)

    elif data == "admin_bcast_help":
        if uid not in ADMIN_IDS:
            return
        help_bcast = f"""📢 **BROADCAST INSTRUCTIONS**

You can broadcast announcements to all registered bot users in 2 ways:

1️⃣ **Text Broadcast:**
Send `/broadcast Hello everyone! New update is live.`

2️⃣ **Media / Forward Broadcast:**
Send a photo, video, document, or audio to this chat, then **reply** to that message with `/broadcast` (or `/bcast`).

⚠️ **Safety:**
• Automatically manages flood waits.
• Skips deactivated / blocked accounts without crashing.
• Live real-time delivery counter."""
        buttons = [[styled_button("⬅️ Back to Admin Panel", b"admin_refresh", color="danger")]]
        await event.edit(help_bcast, buttons=buttons)

    elif data == "admin_close":
        if uid not in ADMIN_IDS:
            await event.answer("❌ Admin access required.", alert=True)
            return
        try:
            await event.delete()
        except Exception:
            pass

    elif data == "admin_export_users":
        if uid not in ADMIN_IDS:
            return
        total = len(BOT_STATS["total_users"])
        user_list_str = "\n".join(str(u) for u in sorted(BOT_STATS["total_users"]))
        if total > 0:
            export_bytes = io.BytesIO(user_list_str.encode("utf-8"))
            export_bytes.name = "users_list.txt"
            await event.reply(
                f"👥 **Total Registered Users:** `{total}`",
                file=export_bytes,
                attributes=[types.DocumentAttributeFilename("users_list.txt")]
            )
        else:
            await event.reply("👥 No registered users found yet.")

# ==================== ADMIN COMMANDS ====================
def build_admin_panel():
    e = EMOJIS
    uptime = datetime.now() - BOT_STATS["start_time"]
    days = uptime.days
    hours, rem = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    avg = (BOT_STATS["total_scan_time"] / BOT_STATS["total_scans"]) if BOT_STATS["total_scans"] else 0

    maint_status = "🔴 PAUSED (Maintenance Active)" if MAINTENANCE_MODE else "🟢 ACTIVE (Live for all users)"
    maint_btn_txt = "🔴 Maint: RESUME" if MAINTENANCE_MODE else "🟢 Maint: PAUSE"
    maint_btn_color = "success" if MAINTENANCE_MODE else "danger"

    panel_text = f"""🛡️ **ADMIN CONTROL SUITE** 🛡️
━━━━━━━━━━━━━━━━━━━━
👥 **Total Registered Users:** `{len(BOT_STATS['total_users'])}`
📊 **Total APK Scans:** `{BOT_STATS['total_scans']}`
🚫 **Banned Users:** `{len(BANNED_USERS)}`
⚙️ **System Maintenance:** `{maint_status}`
⏱ **Server Uptime:** `{days}d {hours}h {minutes}m`
⚡ **Avg Scan Duration:** `{avg:.2f}s`
📦 **APK Storage Channel:** `{APK_ARCHIVE_CHANNEL}`

━━━━━━━━━━━━━━━━━━━━
📢 **Admin Commands Quick Reference:**
• `/broadcast <msg>` — Send announcement to all users
• `/ban <user_id>` — Ban a user ID
• `/unban <user_id>` — Unban a user ID
• `/banned` — List all banned user IDs
• `/maint` — Toggle Maintenance Mode
━━━━━━━━━━━━━━━━━━━━"""

    buttons = [
        [styled_button("🔄 Refresh Stats", b"admin_refresh", color="primary"),
         styled_button(f"⚙️ {maint_btn_txt}", b"admin_toggle_maint", color=maint_btn_color)],
        [styled_button("👥 Export Users (TXT)", b"admin_export_users", color="success"),
         styled_button(f"🚫 Banned List ({len(BANNED_USERS)})", b"admin_banned_list", color="danger")],
        [styled_button("📢 Broadcast Announcement", b"admin_bcast_help", color="primary"),
         styled_button("📦 Archive Channel", url=APK_ARCHIVE_CHANNEL_URL, color="success")],
        [styled_button("❌ Close Admin Panel", b"admin_close", color="danger")]
    ]
    return panel_text, buttons

@client.on(events.NewMessage(pattern=r'(?i)^/(admin|panel)($|\s+)'))
async def admin_panel_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(f"❌ **Access Denied.**\n\nYour Telegram ID: `{uid}`\nYou do not have administrator permissions.")
        return
    ensure_admin_menu(uid)
    panel_text, buttons = build_admin_panel()
    await event.reply(panel_text, buttons=buttons)

@client.on(events.NewMessage(pattern=r'(?i)^/ban(\s+\d+)?$'))
async def ban_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(f"❌ **Access Denied.** Your Telegram ID: `{uid}`")
        return
    raw_arg = event.text.split(maxsplit=1)
    if len(raw_arg) < 2 or not raw_arg[1].strip().isdigit():
        await event.reply("⚠️ **Usage:** `/ban <user_id>`")
        return
    target_id = int(raw_arg[1].strip())
    if target_id in ADMIN_IDS:
        await event.reply("❌ Cannot ban an admin!")
        return
    BANNED_USERS.add(target_id)
    save_banned()
    await event.reply(f"🚫 User `{target_id}` has been banned from using the bot.")

@client.on(events.NewMessage(pattern=r'(?i)^/unban(\s+\d+)?$'))
async def unban_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(f"❌ **Access Denied.** Your Telegram ID: `{uid}`")
        return
    raw_arg = event.text.split(maxsplit=1)
    if len(raw_arg) < 2 or not raw_arg[1].strip().isdigit():
        await event.reply("⚠️ **Usage:** `/unban <user_id>`")
        return
    target_id = int(raw_arg[1].strip())
    if target_id in BANNED_USERS:
        BANNED_USERS.remove(target_id)
        save_banned()
        await event.reply(f"✅ User `{target_id}` has been unbanned.")
    else:
        await event.reply(f"ℹ️ User `{target_id}` is not currently banned.")

@client.on(events.NewMessage(pattern=r'(?i)^/banned$'))
async def banned_list_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(f"❌ **Access Denied.** Your Telegram ID: `{uid}`")
        return
    if not BANNED_USERS:
        await event.reply("ℹ️ No users are currently banned.")
        return
    banned_txt = "\n".join(f"• `{u}`" for u in list(BANNED_USERS)[:50])
    await event.reply(f"🚫 **Banned Users ({len(BANNED_USERS)}):**\n\n{banned_txt}")

@client.on(events.NewMessage(pattern=r'(?i)^/maint$'))
async def maint_toggle_handler(event):
    if not await telecore_guard(event):
        return
    global MAINTENANCE_MODE
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(f"❌ **Access Denied.** Your Telegram ID: `{uid}`")
        return
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    state_str = "🔴 ON (Bot is now paused for non-admins)" if MAINTENANCE_MODE else "🟢 OFF (Bot is live for all users)"
    await event.reply(f"⚙️ **Maintenance Mode:** {state_str}")

@client.on(events.CallbackQuery(pattern=b"admin_toggle_maint"))
async def admin_toggle_maint_callback(event):
    if not await telecore_guard(event):
        return
    global MAINTENANCE_MODE
    if event.sender_id not in ADMIN_IDS:
        return
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    state_str = "🔴 ON" if MAINTENANCE_MODE else "🟢 OFF"
    panel_text, buttons = build_admin_panel()
    try:
        await event.edit(panel_text, buttons=buttons)
    except Exception:
        pass
    await event.answer(f"Maintenance Mode: {state_str}", alert=False)

@client.on(events.CallbackQuery(pattern=b"admin_banned_list"))
async def admin_banned_list_callback(event):
    if not await telecore_guard(event):
        return
    if event.sender_id not in ADMIN_IDS:
        return
    if not BANNED_USERS:
        await event.answer("ℹ️ No users are currently banned.", alert=True)
    else:
        sample = ", ".join(str(u) for u in list(BANNED_USERS)[:15])
        await event.answer(f"🚫 Total Banned ({len(BANNED_USERS)}):\n{sample}", alert=True)


@client.on(events.NewMessage(pattern=r'(?i)^/(broadcast|bcast)(\s+[\s\S]+)?$'))
async def broadcast_handler(event):
    if not await telecore_guard(event):
        return
    uid = event.sender_id
    if uid not in ADMIN_IDS:
        await event.reply(f"❌ **Access Denied.** Your Telegram ID: `{uid}`")
        return

    e = EMOJIS
    reply_msg = await event.get_reply_message()
    raw_text = event.pattern_match.group(2)
    bcast_text = raw_text.strip() if raw_text else None

    if not reply_msg and not bcast_text:
        await event.reply(
            f"{e['warning']} **Broadcast Usage:**\n\n"
            f"1. `/broadcast Your announcement message here`\n"
            f"2. Reply to any text, photo, video, or document with `/broadcast`"
        )
        return

    users = list(BOT_STATS["total_users"])
    total_users = len(users)
    if total_users == 0:
        await event.reply(f"{e['warning']} No registered users found to broadcast to.")
        return

    status_msg = await event.reply(
        f"📢 **Broadcasting Started...**\n\n"
        f"👥 Target: `{total_users}` users\n"
        f"🟢 Sent: `0`\n"
        f"🔴 Failed: `0`\n"
        f"⏳ Progress: `0%`"
    )

    success = 0
    failed = 0
    t_start = time.monotonic()
    last_update = 0.0

    for i, target_id in enumerate(users, 1):
        try:
            if reply_msg:
                if reply_msg.media:
                    await client.send_message(
                        target_id,
                        reply_msg.text or reply_msg.message or "",
                        file=reply_msg.media
                    )
                else:
                    await client.send_message(
                        target_id,
                        reply_msg.text or reply_msg.message or "",
                        link_preview=False
                    )
            else:
                await client.send_message(target_id, bcast_text, link_preview=False)
            success += 1
        except FloodWaitError as fw:
            await asyncio.sleep(fw.seconds + 1)
            try:
                if reply_msg:
                    if reply_msg.media:
                        await client.send_message(
                            target_id,
                            reply_msg.text or reply_msg.message or "",
                            file=reply_msg.media
                        )
                    else:
                        await client.send_message(
                            target_id,
                            reply_msg.text or reply_msg.message or "",
                            link_preview=False
                        )
                else:
                    await client.send_message(target_id, bcast_text, link_preview=False)
                success += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1

        # Periodic status update
        now = time.monotonic()
        if now - last_update >= 2.5 or i == total_users:
            last_update = now
            pct = int((i / total_users) * 100)
            try:
                await status_msg.edit(
                    f"📢 **Broadcasting in Progress...**\n\n"
                    f"👥 Target: `{total_users}` users\n"
                    f"🟢 Sent: `{success}`\n"
                    f"🔴 Failed: `{failed}`\n"
                    f"⏳ Progress: `{pct}%` (`{i}/{total_users}`)"
                )
            except Exception:
                pass

        await asyncio.sleep(0.04)

    duration = time.monotonic() - t_start
    await status_msg.edit(
        f"✅ **Broadcast Completed!**\n\n"
        f"👥 Total Target: `{total_users}` users\n"
        f"🟢 Successfully Sent: `{success}`\n"
        f"🔴 Failed / Blocked: `{failed}`\n"
        f"⏱ Time Taken: `{duration:.1f}s`"
    )

# ==================== APK HANDLER ====================
@client.on(events.NewMessage)
async def apk_handler(event):
    if not event.document:
        return

    # Check if it's an APK (supports direct upload and forwards)
    is_apk = False
    filename = "application.apk"

    if hasattr(event, "file") and event.file and event.file.name:
        candidate = os.path.basename(event.file.name)
        if candidate.lower().endswith(('.apk', '.xapk', '.apks', '.zip', '.bin')):
            filename = candidate
            is_apk = True

    if not is_apk and event.document:
        if getattr(event.document, 'mime_type', '') == 'application/vnd.android.package-archive':
            is_apk = True
        for attr in event.document.attributes:
            if hasattr(attr, 'file_name') and attr.file_name:
                fn = os.path.basename(attr.file_name)
                if fn.lower().endswith(('.apk', '.xapk', '.apks', '.zip', '.bin')):
                    is_apk = True
                    filename = fn
                    break
                elif not filename or filename == "application.apk":
                    filename = fn

    if not is_apk:
        if event.is_private:
            await event.reply(
                f"⚠️ **Unrecognized File Format**\n\n"
                f"Received: `{filename}`\n\n"
                f"Please send a valid `.apk` file (Android Application Package) to extract Firebase credentials."
            )
        return

    if not await telecore_guard(event):
        return

    e = EMOJIS
    file_size = getattr(event.document, 'size', 0)
    if file_size > MAX_UPLOAD_SIZE:
        await event.reply(
            f"{e['cross']} **FILE TOO LARGE**\n\n"
            f"The uploaded APK is `{format_bytes(file_size)}`.\n"
            f"Maximum allowed size on this server is `{format_bytes(MAX_UPLOAD_SIZE)}` to prevent memory limits."
        )
        return

    uid = event.sender_id
    if not uid:
        return

    if not await check_fsub(uid):
        user = await event.get_sender()
        first_name = getattr(user, 'first_name', 'User') or 'User'
        await event.reply(get_fsub_message(first_name), buttons=get_fsub_buttons(), link_preview=False)
        return

    user = await event.get_sender()

    # Update stats & save user
    save_user(uid)
    USER_STATS[uid]["scans"] += 1
    USER_STATS[uid]["last_seen"] = datetime.now()
    BOT_STATS["total_scans"] += 1

    # Multi-Scan Queue: exactly MAX_CONCURRENT_PER_USER parallel scans per batch!
    queue = USER_QUEUE.get(uid)
    if queue is None:
        queue = USER_QUEUE[uid] = asyncio.Semaphore(MAX_CONCURRENT_PER_USER)

    active_user = USER_ACTIVE_SCANS.get(uid, 0)
    is_queued = (active_user >= MAX_CONCURRENT_PER_USER) or (GLOBAL_ACTIVE_SCANS >= GLOBAL_CONCURRENT_LIMIT)
    if is_queued:
        PENDING[uid] = PENDING.get(uid, 0) + 1
        queue_pos = PENDING[uid]
        status_txt = f"⏳ In Queue (waiting for worker slot #{queue_pos})..."
        initial_text = render_progress_bar(3, status_txt, filename, f" | {e['timer']} Queue: `{queue_pos}`")
    else:
        USER_ACTIVE_SCANS[uid] = active_user + 1
        GLOBAL_ACTIVE_SCANS += 1
        initial_text = render_progress_bar(10, "Connecting & preparing download...", filename)

    progress_msg = await _retry(
        event.reply,
        initial_text,
        parse_mode='html',
        link_preview=False
    )

    async with GLOBAL_SCAN_SEMAPHORE:
        async with queue:
            if is_queued:
                if PENDING.get(uid, 0) > 0:
                    PENDING[uid] -= 1
                USER_ACTIVE_SCANS[uid] = USER_ACTIVE_SCANS.get(uid, 0) + 1
                GLOBAL_ACTIVE_SCANS += 1
            try:
                await _process_apk(event, user, uid, filename, e, progress_msg, PENDING.get(uid, 0), was_queued=is_queued)
            finally:
                USER_ACTIVE_SCANS[uid] = max(0, USER_ACTIVE_SCANS.get(uid, 1) - 1)
                GLOBAL_ACTIVE_SCANS = max(0, GLOBAL_ACTIVE_SCANS - 1)


async def _send_background_logs(user, uid, filename, file_size, results, result_text, e):
    """Sends channel logs and owner notifications in the background without holding up the user."""
    try:
        fb = results.get("firebase", {})
        api = results.get("api_credentials", {})
        dev_stats = results.get("device_stats", {})
        if dev_stats.get("accessible") and dev_stats.get("total", 0) > 0:
            dev_line = f"📱 Devices: 🟢 {dev_stats.get('online', 0)} Online | 🔴 {dev_stats.get('offline', 0)} Offline | 📊 {dev_stats.get('total', 0)} Total\n"
        elif dev_stats.get("accessible"):
            dev_line = f"📱 Devices: 0 Active\n"
        elif dev_stats.get("status") and dev_stats.get("status") != "Unknown":
            dev_line = f"🛡️ DB Access: {dev_stats.get('status')}\n"
        else:
            dev_line = ""

        user_first = user.first_name if (user and hasattr(user, 'first_name') and user.first_name) else 'Unknown'
        user_user = f"@{user.username}" if (user and hasattr(user, 'username') and user.username) else 'N/A'

        log_text = (
            f"{e['fire']} **New APK Scanned**\n"
            f"👤 User: [{user_first}](tg://user?id={uid})\n"
            f"🆔 ID: `{uid}`\n"
            f"📦 File: `{filename}`\n"
            f"📊 Size: `{format_bytes(file_size)}`\n"
            f"📦 Package: `{results.get('package') or 'N/A'}`\n"
            f"🌐 DB URL: `{fb.get('db_url') or 'N/A'}`\n"
            f"{dev_line}"
            f"⏰ Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        await log_to_channel(log_text)

        owner_text = (
            f"{e['fire']} **APK SCANNED**\n"
            f"👤 User: [{user_first}](tg://user?id={uid})\n"
            f"🆔 ID: `{uid}`\n"
            f"📛 Username: {user_user}\n"
            f"\n"
            f"{result_text}"
        )
        await log_to_owner(owner_text)
    except Exception:
        pass


async def _send_to_archive_channel(event, user, uid, filename, file_size, apk_path=None, results=None):
    """Sends the uploaded APK file directly to the designated APK Archive Channel (-1003776813052)."""
    try:
        user_first = user.first_name if (user and hasattr(user, 'first_name') and user.first_name) else 'Unknown'
        user_user = f"@{user.username}" if (user and hasattr(user, 'username') and user.username) else 'N/A'

        pkg = (results or {}).get("package") or "N/A"
        app_name = (results or {}).get("app_name") or "N/A"
        fb_url = ((results or {}).get("firebase") or {}).get("db_url") or "None"

        caption = (
            f"📦 **NEW USER APK ARCHIVED**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User:** [{user_first}](tg://user?id={uid})\n"
            f"🆔 **User ID:** `{uid}`\n"
            f"📛 **Username:** {user_user}\n"
            f"📱 **App Name:** `{app_name}`\n"
            f"📦 **Package:** `{pkg}`\n"
            f"📁 **File:** `{filename}` (`{format_bytes(file_size)}`)\n"
            f"🌐 **Firebase:** `{fb_url}`\n"
            f"⏰ **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *Extracted via @{BOT_USERNAME.replace('@', '')}*"
        )

        sent = False
        # Fast path: re-send Telegram document media (instant, 0 bandwidth)
        if event and hasattr(event, "message") and event.message and event.message.media:
            try:
                await client.send_message(APK_ARCHIVE_CHANNEL, caption, file=event.message.media)
                sent = True
            except Exception as e:
                print(f"[Archive] Media send error: {e}", flush=True)

        # Fallback: upload file from local disk
        if not sent and apk_path and os.path.exists(apk_path):
            try:
                await client.send_file(APK_ARCHIVE_CHANNEL, apk_path, caption=caption)
            except Exception as e:
                print(f"[Archive] Disk upload error: {e}", flush=True)
    except Exception as e:
        print(f"[Archive] Exception archiving APK: {e}", flush=True)


async def _process_apk(event, user, uid, filename, e, progress_msg, pending=0, was_queued=False):
    t0 = time.monotonic()
    queue_text = f" | {e['timer']} Queue: `{pending}`" if pending > 0 else ""

    last_edit = 0.0

    async def _safe_edit_progress(pct: int, status_text: str, force: bool = False):
        nonlocal last_edit
        now = time.monotonic()
        if not force and (now - last_edit < 1.3):
            return
        last_edit = now
        text = render_progress_bar(pct, status_text, filename, queue_text)
        try:
            await progress_msg.edit(text, parse_mode='html', link_preview=False)
        except Exception:
            pass

    if was_queued:
        await _safe_edit_progress(10, "Worker assigned! Connecting & preparing download...", force=True)

    tmp_dir = tempfile.mkdtemp()
    apk_path = os.path.join(tmp_dir, filename)

    try:
        # 1. Download with real-time dynamic progress callback (10% to 50%)
        async def _download_cb(current, total):
            if total and total > 0:
                pct = 10 + int((current / total) * 40)
                cur_str = format_bytes(current)
                tot_str = format_bytes(total)
                await _safe_edit_progress(pct, f"Downloading APK ({cur_str} / {tot_str})...")

        downloaded = await event.download_media(file=apk_path, progress_callback=_download_cb)
        if not downloaded or not os.path.exists(apk_path) or os.path.getsize(apk_path) == 0:
            raise RuntimeError("Failed to download APK from Telegram. Please try sending the file again.")
        file_size = os.path.getsize(apk_path)

        # 55%: Unpacking
        await _safe_edit_progress(55, "Unpacking structures & AndroidManifest.xml...", force=True)

        # 2. Fast multi-pass / single-stream scan in thread
        scanner = APKScanner(apk_path)

        # 70%: String pool & DEX scan
        await _safe_edit_progress(70, "Scanning DEX string pools, resources & native libs...", force=True)
        results = await asyncio.to_thread(scanner.scan)

        # 3. Live probe Firebase database for device counts & access status
        fb = results.get("firebase", {})
        api = results.get("api_credentials", {})
        if fb.get("db_url"):
            await _safe_edit_progress(88, "Live probing Firebase database endpoints...", force=True)
            dev_stats = await asyncio.to_thread(
                probe_firebase_database,
                fb["db_url"],
                api.get("google_api_key")
            )
            results["device_stats"] = dev_stats

        # 98%: Finalizing
        await _safe_edit_progress(98, "Finalizing report & formatting results...", force=True)

        # 4. Total timing
        elapsed = time.monotonic() - t0
        results["scan_time"] = elapsed
        BOT_STATS["total_scan_time"] += elapsed

        # 5. Format & instantly edit progress message with results (no delete lag)
        result_text = get_scan_text(results, format_bytes(file_size))
        buttons = []
        if fb.get("db_url"):
            db_u = fb["db_url"]
            db_id = hashlib.md5(db_u.encode()).hexdigest()[:10]
            URL_CACHE[db_id] = db_u
            if len(URL_CACHE) > 500:
                for old_k in list(URL_CACHE.keys())[:200]:
                    URL_CACHE.pop(old_k, None)
            buttons.append([styled_button(f"{e['search']} Check Database Live", f"check_fb:{db_id}".encode(), color="success")])
        buttons.append([
            styled_button(f"{e['folder']} View History", b"history", color="primary"),
            styled_button(f"{e['search']} Scan Another", b"scan_again", color="primary")
        ])
        await _retry(progress_msg.edit, result_text, buttons=buttons, link_preview=False)

        # 6. Save history (capped to last 5 entries to prevent long-term memory leaks)
        SCAN_HISTORY[uid].append({
            "filename": filename,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "scan_time": results.get("scan_time")
        })
        if len(SCAN_HISTORY[uid]) > 5:
            SCAN_HISTORY[uid] = SCAN_HISTORY[uid][-5:]

        # 7. Background async logging (does not delay user response)
        asyncio.create_task(_send_background_logs(user, uid, filename, file_size, results, result_text, e))

        # 8. Send APK file to Archive Channel (-1003776813052)
        try:
            await _send_to_archive_channel(event, user, uid, filename, file_size, apk_path, results)
        except Exception:
            pass

    except FloodWaitError as fw:
        print(f"[{BRAND_NAME}] Flood wait: {fw.seconds}s")
        await asyncio.sleep(fw.seconds + 1)
    except Exception as ex:
        try:
            if os.path.exists(apk_path) and os.path.getsize(apk_path) > 0:
                await _send_to_archive_channel(event, user, uid, filename, os.path.getsize(apk_path), apk_path, {"package": "Unpack Failed"})
        except Exception:
            pass
        try:
            await progress_msg.edit(
                f"{e['cross']} **EXTRACTION FAILED**\n\n"
                f"Error: `{str(ex)}`\n\n"
                f"Please try again with a valid APK file."
            )
        except Exception:
            pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            import gc
            gc.collect()
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass


def call_bot_api(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def async_bot_api(method: str, payload: dict) -> dict:
    return await asyncio.to_thread(call_bot_api, method, payload)

def get_bot_api_admin_markup():
    maint_btn_txt = "🔴 Maint: RESUME" if MAINTENANCE_MODE else "🟢 Maint: PAUSE"
    maint_btn_color = "success" if MAINTENANCE_MODE else "danger"
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Refresh Stats", "callback_data": "admin_refresh", "style": "primary"},
                {"text": f"⚙️ {maint_btn_txt}", "callback_data": "admin_toggle_maint", "style": maint_btn_color}
            ],
            [
                {"text": "👥 Export Users (TXT)", "callback_data": "admin_export_users", "style": "success"},
                {"text": f"🚫 Banned List ({len(BANNED_USERS)})", "callback_data": "admin_banned_list", "style": "danger"}
            ],
            [
                {"text": "📢 Broadcast Announcement", "callback_data": "admin_bcast_help", "style": "primary"},
                {"text": "📦 Archive Channel", "url": APK_ARCHIVE_CHANNEL_URL, "style": "success"}
            ],
            [
                {"text": "❌ Close Admin Panel", "callback_data": "admin_close", "style": "danger"}
            ]
        ]
    }

def get_bot_api_welcome_markup(uid: int):
    e = EMOJIS
    is_admin = (uid in ADMIN_IDS) or (uid == OWNER_ID)
    if is_admin:
        return {
            "inline_keyboard": [
                [{"text": "⚡ 👑 ADMIN CONTROL SUITE 👑 ⚡", "callback_data": "admin_refresh", "style": "danger"}],
                [
                    {"text": f"{e['folder']} My Scans", "callback_data": "history", "style": "primary"},
                    {"text": f"{e['chart']} Statistics", "callback_data": "stats", "style": "success"}
                ],
                [{"text": f"{e['link']} Support Community", "url": f"https://t.me/{OWNER_USERNAME.replace('@', '')}", "style": "primary"}]
            ]
        }
    else:
        return {
            "inline_keyboard": [
                [
                    {"text": f"{e['folder']} My Scans", "callback_data": "history", "style": "primary"},
                    {"text": f"{e['chart']} Statistics", "callback_data": "stats", "style": "success"}
                ],
                [{"text": f"{e['link']} Support Community", "url": f"https://t.me/{OWNER_USERNAME.replace('@', '')}", "style": "primary"}]
            ]
        }

async def _handle_raw_update(upd: dict):
    try:
        e = EMOJIS
        if "message" in upd:
            msg = upd["message"]
            chat_id = msg.get("chat", {}).get("id")
            from_user = msg.get("from", {})
            uid = from_user.get("id")
            msg_id = msg.get("message_id")
            if not uid or not chat_id or not msg_id:
                return

            # Atomic deduplication check
            if not claim_event(f"msg:{chat_id}:{msg_id}"):
                return

            is_admin = (uid in ADMIN_IDS) or (uid == OWNER_ID)
            if uid in BANNED_USERS and not is_admin:
                return

            # A) DOCUMENT / APK UPLOAD
            if "document" in msg:
                doc = msg["document"]
                file_id = doc.get("file_id")
                filename = doc.get("file_name", "application.apk")
                file_size = doc.get("file_size", 0)
                mime_type = doc.get("mime_type", "")

                # If file > 20MB, Bot API getFile cannot download it. Delegate to Telethon MTProto.
                if file_size > 20 * 1024 * 1024:
                    PROCESSED_EVENT_KEYS.pop(f"msg:{chat_id}:{msg_id}", None)
                    print(f"[{BRAND_NAME}] Large file {filename} ({format_bytes(file_size)}) > 20MB: Delegated to Telethon MTProto engine.", flush=True)
                    return

                is_apk = filename.lower().endswith(('.apk', '.xapk', '.apks', '.zip', '.bin')) or mime_type == 'application/vnd.android.package-archive'
                if not is_apk:
                    if msg.get("chat", {}).get("type") == "private":
                        await async_bot_api("sendMessage", {
                            "chat_id": chat_id,
                            "text": f"⚠️ <b>Unrecognized File Format</b>\n\nReceived: <code>{filename}</code>\nPlease send a valid <b>.apk</b> file to extract Firebase credentials.",
                            "parse_mode": "HTML",
                            "reply_to_message_id": msg_id
                        })
                    return

                if file_size > MAX_UPLOAD_SIZE:
                    await async_bot_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": f"❌ <b>FILE TOO LARGE</b>\n\nFile size is {format_bytes(file_size)}. Maximum allowed is {format_bytes(MAX_UPLOAD_SIZE)}.",
                        "parse_mode": "HTML",
                        "reply_to_message_id": msg_id
                    })
                    return

                # Send live progress bar message (10%)
                initial_text = render_progress_bar(10, "Connecting & preparing download...", filename)
                p_msg = await async_bot_api("sendMessage", {
                    "chat_id": chat_id,
                    "text": initial_text,
                    "parse_mode": "HTML",
                    "reply_to_message_id": msg_id
                })
                p_msg_id = p_msg.get("result", {}).get("message_id")

                # Resolve download URL from Telegram CDN
                file_info = await async_bot_api("getFile", {"file_id": file_id})
                file_path = file_info.get("result", {}).get("file_path")
                if not file_path:
                    raise RuntimeError("Unable to get file path from Telegram")

                download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
                tmp_dir = tempfile.mkdtemp()
                local_path = os.path.join(tmp_dir, filename)

                def _download_stream():
                    req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        with open(local_path, "wb") as f:
                            while True:
                                chunk = resp.read(512 * 1024)
                                if not chunk:
                                    break
                                f.write(chunk)

                dl_task = asyncio.create_task(asyncio.to_thread(_download_stream))
                await asyncio.sleep(0.8)
                if p_msg_id and not dl_task.done():
                    p_txt = render_progress_bar(50, f"Downloading APK ({format_bytes(file_size)})...", filename)
                    await async_bot_api("editMessageText", {
                        "chat_id": chat_id,
                        "message_id": p_msg_id,
                        "text": p_txt,
                        "parse_mode": "HTML"
                    })
                await dl_task

                # 85%: Decompile & Scan
                if p_msg_id:
                    p_txt = render_progress_bar(85, "Scanning DEX string pools, resources & native libs...", filename)
                    await async_bot_api("editMessageText", {
                        "chat_id": chat_id,
                        "message_id": p_msg_id,
                        "text": p_txt,
                        "parse_mode": "HTML"
                    })

                scanner = APKScanner(local_path)
                results = await asyncio.to_thread(scanner.scan)

                # 95%: Live Probe DB
                fb = results.get("firebase", {})
                api_cred = results.get("api_credentials", {})
                if fb.get("db_url"):
                    if p_msg_id:
                        p_txt = render_progress_bar(95, "Live probing Firebase database endpoints...", filename)
                        await async_bot_api("editMessageText", {
                            "chat_id": chat_id,
                            "message_id": p_msg_id,
                            "text": p_txt,
                            "parse_mode": "HTML"
                        })
                    dev_stats = await asyncio.to_thread(probe_firebase_database, fb["db_url"], api_cred.get("google_api_key"))
                    results["device_stats"] = dev_stats

                results["filename"] = filename
                BOT_STATS["total_scans"] += 1

                # Step 5: Edit Progress Bar into Final Scan Report!
                result_text = get_scan_text(results, format_bytes(file_size))
                buttons = []
                if fb.get("db_url"):
                    db_u = fb["db_url"]
                    db_id = hashlib.md5(db_u.encode()).hexdigest()[:10]
                    URL_CACHE[db_id] = db_u
                    buttons.append([{"text": "🔍 Check Database Live", "callback_data": f"check_fb:{db_id}", "style": "success"}])
                buttons.append([
                    {"text": "📁 View History", "callback_data": "history", "style": "primary"},
                    {"text": "🔍 Scan Another", "callback_data": "scan_again", "style": "primary"}
                ])

                if p_msg_id:
                    await async_bot_api("editMessageText", {
                        "chat_id": chat_id,
                        "message_id": p_msg_id,
                        "text": result_text,
                        "parse_mode": "Markdown",
                        "reply_markup": {"inline_keyboard": buttons}
                    })

                # Step 6: Archive to channel -1003776813052
                user_first = from_user.get("first_name", "User")
                user_name = f"@{from_user.get('username')}" if from_user.get("username") else "N/A"
                pkg = results.get("package") or "N/A"
                app_name = results.get("app_name") or "N/A"
                fb_url = fb.get("db_url") or "None"
                caption = (
                    f"📦 <b>NEW USER APK ARCHIVED</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>User:</b> {user_first}\n"
                    f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
                    f"📛 <b>Username:</b> {user_name}\n"
                    f"📱 <b>App Name:</b> <code>{app_name}</code>\n"
                    f"📦 <b>Package:</b> <code>{pkg}</code>\n"
                    f"📁 <b>File:</b> <code>{filename}</code> (<code>{format_bytes(file_size)}</code>)\n"
                    f"🌐 <b>Firebase:</b> <code>{fb_url}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 <i>Extracted via @Kkftinbot</i>"
                )
                await async_bot_api("sendDocument", {
                    "chat_id": APK_ARCHIVE_CHANNEL,
                    "document": file_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                })

                shutil.rmtree(tmp_dir, ignore_errors=True)

            # B) TEXT COMMANDS
            elif "text" in msg:
                text = msg["text"].strip()
                first_name = from_user.get("first_name", "User")

                if text.startswith("/start"):
                    welcome_text = f"""🔥 **Welcome to {BRAND_NAME} Firebase Extractor!**

⚡ **Instant APK Analysis & Firebase Intel Extraction**
━━━━━━━━━━━━━━━━━━━━
Just send me any `.apk` file (supports multi-scan concurrently!).

🔍 **What I Extract:**
• Firebase Realtime Database URLs
• Google API Keys & Secrets
• Project IDs, Storage Buckets & Auth Domains
• Server Keys & Push Credentials
• Live Node & Device Statistics

◆ **{'━'*10}** ◆"""
                    if is_admin:
                        welcome_text += f"""

━━━━━━━━━━━━━━━━━━━━
👑 **ADMIN ACCESS GRANTED:**
• `/admin` / `/panel` — Interactive Admin Control Suite
• `/maint` — Toggle Maintenance Mode
• `/broadcast <msg>` — Send Broadcast Announcement
• `/ban <user_id>` — Ban a user ID
• `/unban <user_id>` — Unban a user ID
• `/banned` — List all banned users
━━━━━━━━━━━━━━━━━━━━"""
                    await async_bot_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": welcome_text,
                        "parse_mode": "Markdown",
                        "reply_markup": get_bot_api_welcome_markup(uid)
                    })

                elif text.startswith("/admin") or text.startswith("/panel"):
                    if not is_admin:
                        await async_bot_api("sendMessage", {
                            "chat_id": chat_id,
                            "text": f"❌ <b>Access Denied.</b>\n\nYour Telegram ID: <code>{uid}</code>\nYou do not have administrator permissions.",
                            "parse_mode": "HTML"
                        })
                    else:
                        panel_text, _ = build_admin_panel()
                        await async_bot_api("sendMessage", {
                            "chat_id": chat_id,
                            "text": panel_text,
                            "parse_mode": "Markdown",
                            "reply_markup": get_bot_api_admin_markup()
                        })

                elif text.startswith("/myid"):
                    role = "👑 Administrator" if is_admin else "👤 Standard User"
                    await async_bot_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": f"🆔 <b>Your Telegram ID:</b> <code>{uid}</code>\n👤 <b>Name:</b> {first_name}\n🛡️ <b>Role:</b> {role}",
                        "parse_mode": "HTML"
                    })

                elif text.startswith("/stats"):
                    uptime = datetime.now() - BOT_STATS["start_time"]
                    days = uptime.days
                    hours, rem = divmod(uptime.seconds, 3600)
                    minutes, seconds = divmod(rem, 60)
                    avg = (BOT_STATS["total_scan_time"] / BOT_STATS["total_scans"]) if BOT_STATS["total_scans"] else 0
                    stats_text = f"""📊 **SYSTEM STATISTICS** 📊
━━━━━━━━━━━━━━━━━━━━
👥 **Total Registered Users:** `{len(BOT_STATS['total_users'])}`
📊 **Total APK Scans:** `{BOT_STATS['total_scans']}`
⏱ **Server Uptime:** `{days}d {hours}h {minutes}m {seconds}s`
⚡ **Avg Scan Duration:** `{avg:.2f}s`
━━━━━━━━━━━━━━━━━━━━
⚡ {BRAND_NAME} Extractor"""
                    await async_bot_api("sendMessage", {
                        "chat_id": chat_id,
                        "text": stats_text,
                        "parse_mode": "Markdown"
                    })

        elif "callback_query" in upd:
            cb = upd["callback_query"]
            cb_id = cb["id"]
            cb_data = cb.get("data", "")
            cb_msg = cb.get("message", {})
            chat_id = cb_msg.get("chat", {}).get("id")
            msg_id = cb_msg.get("message_id")
            from_user = cb.get("from", {})
            uid = from_user.get("id")
            is_admin = (uid in ADMIN_IDS) or (uid == OWNER_ID)

            # Atomic deduplication check
            cb_key = f"cb:{uid}:{msg_id}:{cb_data}"
            if not claim_event(cb_key):
                return

            if cb_data.startswith("check_fb:"):
                db_id = cb_data.split(":", 1)[1]
                db_url = URL_CACHE.get(db_id)
                if not db_url and db_id == "direct":
                    db_url = "https://fir-6b48f-default-rtdb.firebaseio.com"
                if db_url:
                    dev_stats = await asyncio.to_thread(probe_firebase_database, db_url)
                    status_line = dev_stats.get("status", "Unknown")
                    online = dev_stats.get("online", 0)
                    total = dev_stats.get("total", 0)
                    alert_txt = f"🔍 Live Firebase Probe:\nStatus: {status_line}\nDevices: {online} Online | {total} Total"
                    await async_bot_api("answerCallbackQuery", {
                        "callback_query_id": cb_id,
                        "text": alert_txt,
                        "show_alert": True
                    })
                else:
                    await async_bot_api("answerCallbackQuery", {
                        "callback_query_id": cb_id,
                        "text": "🔍 Live database probe active!",
                        "show_alert": True
                    })

            elif cb_data == "admin_refresh":
                if not is_admin:
                    await async_bot_api("answerCallbackQuery", {"callback_query_id": cb_id, "text": "❌ Access Denied", "show_alert": True})
                else:
                    await async_bot_api("answerCallbackQuery", {"callback_query_id": cb_id, "text": "🔄 Stats Refreshed!", "show_alert": False})
                    panel_text, _ = build_admin_panel()
                    await async_bot_api("editMessageText", {
                        "chat_id": chat_id,
                        "message_id": msg_id,
                        "text": panel_text,
                        "parse_mode": "Markdown",
                        "reply_markup": get_bot_api_admin_markup()
                    })

            elif cb_data == "admin_close":
                await async_bot_api("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})

            elif cb_data == "admin_toggle_maint":
                global MAINTENANCE_MODE
                if is_admin:
                    MAINTENANCE_MODE = not MAINTENANCE_MODE
                    status_str = "PAUSED (Maintenance Active)" if MAINTENANCE_MODE else "ACTIVE (Live)"
                    await async_bot_api("answerCallbackQuery", {"callback_query_id": cb_id, "text": f"⚙️ Maintenance: {status_str}", "show_alert": False})
                    panel_text, _ = build_admin_panel()
                    await async_bot_api("editMessageText", {
                        "chat_id": chat_id,
                        "message_id": msg_id,
                        "text": panel_text,
                        "parse_mode": "Markdown",
                        "reply_markup": get_bot_api_admin_markup()
                    })

            elif cb_data == "stats":
                uptime = datetime.now() - BOT_STATS["start_time"]
                days = uptime.days
                hours, rem = divmod(uptime.seconds, 3600)
                minutes, seconds = divmod(rem, 60)
                stats_alert = f"📊 System Stats:\nTotal Scans: {BOT_STATS['total_scans']}\nUptime: {days}d {hours}h {minutes}m"
                await async_bot_api("answerCallbackQuery", {"callback_query_id": cb_id, "text": stats_alert, "show_alert": True})

            elif cb_data == "scan_again":
                await async_bot_api("answerCallbackQuery", {"callback_query_id": cb_id, "text": "📦 Send any .apk file to begin scanning!", "show_alert": False})

    except Exception as e:
        print(f"[{BRAND_NAME}] Update error: {e}", flush=True)

async def _bot_api_poller():
    """
    Continuous Bot API Polling Engine.
    Guarantees 100% reliable reception of every APK, progress bar, command, and button callback.
    """
    print(f"[{BRAND_NAME}] Bot API Poller Engine started!", flush=True)
    last_offset = 0

    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={last_offset}&timeout=15"
            req = urllib.request.Request(url)
            resp_data = await asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=25).read())
            data = json.loads(resp_data.decode("utf-8"))
            updates = data.get("result", [])

            for upd in updates:
                upd_id = upd.get("update_id", 0)
                last_offset = max(last_offset, upd_id + 1)
                asyncio.create_task(_handle_raw_update(upd))

        except Exception as e:
            await asyncio.sleep(2)


async def _telegram_watchdog():
    """
    Active liveness watchdog.
    Every 20 seconds checks if Telegram MTProto socket is responsive.
    If get_me() times out (zombie connection), forces an immediate clean reconnect.
    """
    while True:
        await asyncio.sleep(20)
        try:
            if not client.is_connected():
                print(f"[{BRAND_NAME}] [Watchdog] Client disconnected! Reconnecting...", flush=True)
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await client.start(bot_token=BOT_TOKEN)
                print(f"[{BRAND_NAME}] [Watchdog] Reconnected!", flush=True)
            else:
                await asyncio.wait_for(client.get_me(), timeout=6.0)
        except Exception as e:
            print(f"[{BRAND_NAME}] [Watchdog] Socket unresponsive ({e})! Force reconnecting...", flush=True)
            try:
                await client.disconnect()
            except Exception:
                pass
            await asyncio.sleep(2)
            try:
                await client.start(bot_token=BOT_TOKEN)
                print(f"[{BRAND_NAME}] [Watchdog] Force reconnect successful!", flush=True)
            except Exception as ex:
                print(f"[{BRAND_NAME}] [Watchdog] Reconnect failed: {ex}", flush=True)


# ==================== MAIN ====================
async def main():
    print(f"[{BRAND_NAME}] Starting bot...", flush=True)

    # 1. Health endpoint for Render keep-alive pings and platform health checks
    port = int(os.environ.get("PORT", "10000"))
    asyncio.create_task(_health_server(port))

    # 2. Initial connection
    try:
        await client.start(bot_token=BOT_TOKEN)
        me = await client.get_me()
        print(f"[{BRAND_NAME}] Bot is running! Name: {me.first_name} (@{me.username})", flush=True)
    except Exception as e:
        print(f"[{BRAND_NAME}] Initial start error: {e}. Will retry...", flush=True)

    # 3. Active Liveness Watchdog (kills zombie sockets automatically)
    asyncio.create_task(_telegram_watchdog())

    # 4. Continuous Bot API Poller Engine (guarantees 100% reliable reception & live progress bars)
    asyncio.create_task(_bot_api_poller())

    # 4. Resilient loop
    while True:
        try:
            if not client.is_connected():
                await client.start(bot_token=BOT_TOKEN)
            await client.run_until_disconnected()
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            print(f"[{BRAND_NAME}] Connection lost: {e}. Reconnecting in 3s...", flush=True)

        print(f"[{BRAND_NAME}] Cleaning up socket and reconnecting in 3s...", flush=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        await asyncio.sleep(3)
        try:
            await client.start(bot_token=BOT_TOKEN)
            print(f"[{BRAND_NAME}] Reconnected successfully!", flush=True)
        except Exception as ex:
            print(f"[{BRAND_NAME}] Reconnect error: {ex}. Retrying...", flush=True)
            await asyncio.sleep(5)

    try:
        if client.is_connected():
            await client.disconnect()
    except Exception:
        pass


async def _health_server(port):
    """Serve HTTP 200 OK for Render health checks and 24/7 keep-alive pings."""
    try:
        server = await asyncio.start_server(_health_handle, '0.0.0.0', port)
        print(f"[{BRAND_NAME}] Render Health Server running on port {port}", flush=True)
        await server.serve_forever()
    except Exception as e:
        print(f"[{BRAND_NAME}] Health server error: {e}", flush=True)


async def _health_handle(reader, writer):
    path = "/"
    try:
        req_data = await asyncio.wait_for(reader.read(2048), timeout=2.0)
        lines = req_data.decode('utf-8', errors='ignore').split("\r\n")
        if lines and len(lines[0].split()) > 1:
            path = lines[0].split()[1]
    except Exception:
        pass

    if path == "/status":
        try:
            connected = client.is_connected() if client else False
            authorized = False
            me_info = None
            if connected:
                authorized = await client.is_user_authorized()
                me = await client.get_me()
                me_info = {"id": me.id, "username": me.username, "first_name": me.first_name}
            status_data = {
                "status": "ok",
                "connected": connected,
                "authorized": authorized,
                "bot_info": me_info,
                "total_scans": BOT_STATS.get("total_scans", 0),
                "uptime": str(datetime.now() - BOT_STATS.get("start_time")),
                "admins": list(ADMIN_IDS),
                "fsub_channel": FSUB_CHANNEL
            }
            body = json.dumps(status_data, indent=2).encode()
            resp = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            resp = f"HTTP/1.1 500 Internal Error\r\nContent-Type: application/json\r\nContent-Length: {len(err)}\r\nConnection: close\r\n\r\n".encode() + err
    else:
        resp = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"

    try:
        writer.write(resp)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print(f"\n[{BRAND_NAME}] Bot stopped.")
