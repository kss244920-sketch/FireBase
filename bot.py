import os
import re
import struct
import asyncio
import time
import zipfile
import tempfile
import shutil
from datetime import datetime
from collections import defaultdict

from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
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
BRAND_NAME = os.environ.get("BRAND_NAME", "MARC")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "@Kkftinbot")

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

# ==================== DATA STORAGE ====================
USER_STATS = defaultdict(lambda: {"scans": 0, "first_seen": None, "last_seen": None})
SCAN_HISTORY = defaultdict(list)  # user_id -> list of scan results
BOT_STATS = {"total_scans": 0, "total_users": set(), "total_scan_time": 0.0, "start_time": datetime.now()}

# Per-user lock so one user's many uploads are processed sequentially
# (prevents floods/rate limits) while other users stay responsive.
USER_QUEUE = {}
# Per-user count of APKs still waiting in the queue (used for ETA estimates).
PENDING = {}

# ==================== SPEED / SAFETY SETTINGS ====================
MAX_SCAN_FILE_SIZE = 2 * 1024 * 1024  # skip text files larger than 2MB
DEX_HEAD_BYTES = 512 * 1024           # only read the first 512KB of .dex files
PROGRESS_EDIT_INTERVAL = 0.8          # seconds between progress-message edits

# ==================== ANDROID BINARY XML HELPERS ====================
def _read_utf8_len(data, pos):
    """Read a ResStringPool variable-length UTF-8 length at pos."""
    b = data[pos]
    pos += 1
    if b & 0x80:
        b2 = data[pos]
        pos += 1
        return ((b & 0x7F) << 8) | b2, pos
    return b, pos


def _axml_strings(data):
    """Extract readable strings from an AndroidManifest binary XML string pool."""
    try:
        if len(data) < 28:
            return []
        ctype, hsize, _csize = struct.unpack_from('<HHI', data, 0)
        if ctype != 0x0001 or hsize < 28:
            return []
        string_count, _style_count, flags, strings_start, _styles_start = struct.unpack_from('<IIIII', data, 8)
        if not string_count or strings_start == 0 or strings_start > len(data):
            return []
        utf8 = bool(flags & 0x00000100)
        strings = []
        for i in range(string_count):
            off_pos = hsize + 4 * i
            if off_pos + 4 > len(data):
                break
            (off,) = struct.unpack_from('<I', data, off_pos)
            pos = strings_start + off
            if pos >= len(data):
                continue
            if utf8:
                u16len, pos = _read_utf8_len(data, pos)
                _, pos = _read_utf8_len(data, pos)
                end = data.find(b'\x00', pos)
                if end == -1 or end > pos + u16len * 3 + 4:
                    end = pos + u16len * 3 + 1
                end = min(end, len(data))
                s = data[pos:end].decode('utf-8', errors='ignore')
            else:
                slen = (data[pos] | (data[pos + 1] << 8)) & 0x7FFF
                pos += 2
                end = min(pos + slen * 2, len(data))
                s = data[pos:end].decode('utf-16-le', errors='ignore')
            if s:
                strings.append(s)
        return strings
    except Exception:
        return []


# ==================== APK SCANNER ====================
class APKScanner:
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
            "errors": []
        }

    def scan(self):
        try:
            self._extract_manifest()
            self._scan_resources()
            self._detect_packer()
        except Exception as e:
            self.results["errors"].append(str(e))
        return self.results

    def _extraction_complete(self):
        """Stop scanning early once we have everything we need."""
        fb = self.results["firebase"]
        api = self.results["api_credentials"]
        return (
            bool(fb.get("project_id") or fb.get("db_url"))
            and bool(fb.get("sender_id"))
            and bool(fb.get("storage"))
            and bool(api.get("google_api_key"))
            and bool(api.get("app_id"))
        )

    def _extract_manifest(self):
        """Extract package info from AndroidManifest.xml (binary XML aware)."""
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as z:
                manifest_data = None
                for name in z.namelist():
                    if name.endswith('AndroidManifest.xml'):
                        manifest_data = z.read(name)
                        break

                if not manifest_data:
                    return

                strings = _axml_strings(manifest_data)
                if strings:
                    text = "\n".join(strings)
                    # Package name is usually a java-style dotted string in the pool
                    for s in strings:
                        if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*){2,}', s):
                            self.results["package"] = s
                            break
                    # versionName is a plain dotted number string
                    for s in strings:
                        if re.fullmatch(r'\d+\.\d+[0-9A-Za-z._-]*', s) and s != self.results.get("package"):
                            self.results["version"] = s
                            break
                else:
                    text = manifest_data.decode('utf-8', errors='ignore')

                if not self.results.get("package"):
                    pkg_match = re.search(r'package=["\']([^"\']+)["\']', text)
                    if pkg_match:
                        self.results["package"] = pkg_match.group(1)

                if not self.results.get("version"):
                    ver_match = re.search(r'android:versionName=["\']([^"\']+)["\']', text)
                    if ver_match:
                        self.results["version"] = ver_match.group(1)

                if not self.results.get("build_code"):
                    code_match = re.search(r'android:versionCode=["\']([^"\']+)["\']', text)
                    if code_match:
                        self.results["build_code"] = code_match.group(1)

                # Try to get app name from resources.arsc (size-bounded)
                for name in z.namelist():
                    if 'resources.arsc' in name:
                        try:
                            if z.getinfo(name).file_size <= MAX_SCAN_FILE_SIZE:
                                arsc_data = z.read(name)
                                arsc_text = arsc_data.decode('utf-8', errors='ignore')
                                name_match = re.search(r'app_name.*?([A-Za-z][A-Za-z0-9_\s]{2,30})', arsc_text)
                                if name_match and not self.results["app_name"]:
                                    self.results["app_name"] = name_match.group(1).strip()
                        except Exception:
                            pass
                        break
        except Exception as e:
            self.results["errors"].append(f"Manifest error: {e}")

    def _scan_resources(self):
        """Scan files for Firebase/API patterns with bounded reads + early exit."""
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as z:
                for name in z.namelist():
                    try:
                        info = z.getinfo(name)
                    except KeyError:
                        continue

                    is_dex = name.endswith('.dex')
                    if not name.endswith(('.xml', '.json', '.txt', '.properties', '.smali')) and not is_dex:
                        continue

                    try:
                        if is_dex:
                            if info.file_size > MAX_SCAN_FILE_SIZE:
                                with z.open(name) as f:
                                    text = f.read(DEX_HEAD_BYTES).decode('utf-8', errors='ignore')
                            else:
                                text = z.read(name).decode('utf-8', errors='ignore')
                        else:
                            if info.file_size > MAX_SCAN_FILE_SIZE:
                                continue
                            text = z.read(name).decode('utf-8', errors='ignore')
                    except Exception:
                        continue

                    self._extract_firebase(text)
                    self._extract_api_keys(text)

                    # Early exit: everything found, no need to scan the rest
                    if self._extraction_complete():
                        break
        except Exception as e:
            self.results["errors"].append(f"Resource scan error: {e}")

    def _detect_packer(self):
        """Detect if APK is packed/obfuscated"""
        packers = []
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as z:
                files = z.namelist()

                # Check for known packer signatures
                if any('libjiagu' in f for f in files):
                    packers.append("Jiagu")
                if any('libmobisec' in f for f in files):
                    packers.append("Mobisec")
                if any('libshell' in f for f in files):
                    packers.append("360 Jiagu")
                if any('libbaiduprotect' in f for f in files):
                    packers.append("Baidu Protect")
                if any('libtup' in f for f in files):
                    packers.append("Tencent TUP")
                if any('libedog' in f for f in files):
                    packers.append("Bangcle")
                if any('libchaosvmp' in f for f in files):
                    packers.append("Naga/ChaosVMP")
                if any('libsecexe' in f for f in files):
                    packers.append("SecNeo")
                if any('libprotect' in f for f in files):
                    packers.append("Custom Protect")

                # Check for heavy obfuscation
                dex_files = [f for f in files if f.endswith('.dex')]
                if len(dex_files) > 5:
                    packers.append("Multi-Dex (Possible Obfuscation)")

                # Check for native libs in unusual places
                native_libs = [f for f in files if f.endswith('.so')]
                if len(native_libs) > 20:
                    packers.append("Heavy Native Libs")
        except Exception as e:
            self.results["errors"].append(f"Packer detection error: {e}")

        self.results["packer"] = ", ".join(packers) if packers else "None detected"

    def _extract_firebase(self, text):
        """Extract Firebase configuration from a chunk of scanned text."""
        fb = self.results["firebase"]
        if not text:
            return

        # Firebase Database URL
        if not fb.get("project_id") and not fb.get("db_url"):
            db_match = re.search(r'https://([a-zA-Z0-9_-]+)-default-rtdb\.firebaseio\.com', text)
            if db_match:
                project_id = db_match.group(1)
                fb["db_url"] = f"https://{project_id}-default-rtdb.firebaseio.com"
                fb["project_id"] = project_id
                fb["auth_domain"] = f"{project_id}.firebaseapp.com"
            else:
                alt_db = re.search(r'https://([a-zA-Z0-9_-]+)\.firebaseio\.com', text)
                if alt_db:
                    pid = alt_db.group(1).replace('-default-rtdb', '')
                    fb["db_url"] = alt_db.group(0)
                    fb["project_id"] = pid
                    fb["auth_domain"] = f"{pid}.firebaseapp.com"

        # Google Services JSON pattern / Sender ID
        if not fb.get("sender_id"):
            gservices = re.search(r'"project_info".*?"project_number"\s*:\s*"(\d+)"', text, re.DOTALL)
            if gservices:
                fb["sender_id"] = gservices.group(1)
            else:
                sender_patterns = [
                    r'gcm_defaultSenderId.*?([0-9]{10,20})',
                    r'"sender_id"\s*:\s*"([0-9]{10,20})"',
                    r'project_number.*?([0-9]{10,20})'
                ]
                for pattern in sender_patterns:
                    match = re.search(pattern, text)
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
                match = re.search(pattern, text)
                if match:
                    fb["storage"] = match.group(1)
                    break

        # If we have project_id but no storage, derive it
        if "project_id" in fb and "storage" not in fb:
            fb["storage"] = f"{fb['project_id']}.appspot.com"

    def _extract_api_keys(self, text):
        """Extract API credentials from a chunk of scanned text."""
        api = self.results["api_credentials"]
        if not text:
            return

        # Google API Key
        if not api.get("google_api_key"):
            api_key_patterns = [
                r'AIza[0-9A-Za-z_-]{35}',
                r'"api_key"\s*:\s*"(AIza[0-9A-Za-z_-]{35})"',
                r'current_api_key.*?([A-Za-z0-9_-]{39})'
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

def get_scan_text(results, file_size="Unknown"):
    """Format scan results into message text"""
    e = EMOJIS

    _st = results.get("scan_time")
    scan_time_str = f"{_st:.2f}s" if isinstance(_st, (int, float)) else "Unknown"

    lines = [
        f"{e['check']} **EXTRACTION SUCCESSFUL**",
        "",
        f"━" * 20,
        "",
        f"{e['package']} **APK:** `{results['filename']}`",
        "",
        f"📋 **App Information**",
        f"📄 Package:    `{results.get('package') or 'Not found'}`",
        f"📂 App Name:   {'❌ Not found' if not results.get('app_name') else results['app_name']}",
        f"🔢 Version:    {results.get('version') or '❌ Not found'}",
        f"#️⃣ Build Code: {results.get('build_code') or '❌ Not found'}",
        f"{e['shield']} Packer:     {results.get('packer') or 'None detected'}",
        f"{e['timer']} Scan Time:  `{scan_time_str}`",
        "",
    ]

    # Firebase Config
    fb = results.get("firebase", {})
    lines.append(f"{e['fire']} **Firebase Config**")
    if fb.get("db_url"):
        lines.append(f"{e['globe']} DB URL:   `{fb['db_url']}`")
    else:
        lines.append(f"{e['globe']} DB URL:   ❌ Not found")

    if fb.get("project_id"):
        lines.append(f"{e['id_card']} Project ID: `{fb['project_id']}`")
    else:
        lines.append(f"{e['id_card']} Project ID: ❌ Not found")

    if fb.get("auth_domain"):
        lines.append(f"{e['lock']} Auth Domain: `{fb['auth_domain']}` (derived)")

    if fb.get("sender_id"):
        lines.append(f"{e['bucket']} Sender ID: `{fb['sender_id']}`")
    else:
        lines.append(f"{e['bucket']} Sender ID: ❌ Not found")

    if fb.get("storage"):
        lines.append(f"{e['bucket']} Storage:  `{fb['storage']}`")
    else:
        lines.append(f"{e['bucket']} Storage:  ❌ Not found")

    lines.append("")

    # API Credentials
    api = results.get("api_credentials", {})
    lines.append(f"{e['key']} **API Credentials**")
    if api.get("google_api_key"):
        lines.append(f"🔑 Google API Key:\n`{api['google_api_key']}`")
    else:
        lines.append(f"🔑 Google API Key: ❌ Not found")

    if api.get("app_id"):
        lines.append(f"📱 App ID:\n`{api['app_id']}`")
    else:
        lines.append(f"📱 App ID: ❌ Not found")

    if api.get("oauth_clients"):
        lines.append(f"🔗 OAuth Clients:")
        for client in api["oauth_clients"][:3]:
            lines.append(f"`{client}`")

    lines.append("")
    lines.append(f"━" * 20)
    lines.append(f"{e['zap']} Powered by {BRAND_NAME} {e['rocket']}")

    return "\n".join(lines)

def get_progress_text(filename, step, queue_info=None):
    """Show scanning progress"""
    e = EMOJIS
    steps = [
        ("Initializing scanner", 1),
        ("Downloading APK", 2),
        ("Decompiling APK", 3),
        ("Scanning resources", 4),
        ("Extracting Firebase config", 5),
        ("Finalizing results...", 6)
    ]

    lines = [
        f"{e['gear']} **{'━'*10}** {e['gear']}",
        f"{e['fire']} **FIREBASE EXTRACTOR** {e['fire']}",
        f"{e['gear']} **{'━'*10}** {e['gear']}",
        "",
        f"{e['zap']} **Processing:** `{filename}`",
        "",
    ]

    for i, (desc, num) in enumerate(steps, 1):
        if i < step:
            lines.append(f"{e['check']} {desc}")
        elif i == step:
            lines.append(f"{e['chart']} {desc}...")
        else:
            lines.append(f"⬜ {desc}")

    lines.append("")
    if queue_info:
        lines.append(queue_info)
    lines.append(f"━" * 20)
    return "\n".join(lines)

# ==================== HANDLERS ====================
@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user = await event.get_sender()
    uid = user.id

    # Update stats
    if USER_STATS[uid]["first_seen"] is None:
        USER_STATS[uid]["first_seen"] = datetime.now()
        BOT_STATS["total_users"].add(uid)
    USER_STATS[uid]["last_seen"] = datetime.now()

    e = EMOJIS

    welcome_text = f"""{e['zap']} **{'━'*10}** {e['zap']}
{e['fire']} **FIREBASE EXTRACTOR BOT** {e['fire']}
{e['zap']} **{'━'*10}** {e['zap']}

👋 Hey ❖ **{user.first_name or 'User'}** ❖! Welcome to the most advanced Firebase extractor on Telegram.

◆ **{'━'*10}** ◆

**What I Extract from APKs:**
{e['fire']} Firebase Database URL
{e['key']} Google API Key & App ID
{e['package']} Package name & version
{e['bucket']} GCM Sender ID
{e['bucket']} Project ID & Storage Bucket
{e['shield']} Packer detection

**How to Scan:**
Just send me any `.apk` file and I'll do the rest.
{e['check']} Completely free
{e['check']} No limits
{e['check']} Queue system handles multiple uploads

`/help`   — Commands
`/history` — Your scan history
`/stats`  — Bot statistics
`/myid`   — Your profile

◆ **{'━'*10}** ◆"""

    buttons = [
        [Button.inline(f"{e['folder']} History", b"history"),
         Button.inline(f"{e['chart']} Stats", b"stats")],
        [Button.url(f"{e['link']} Support", f"https://t.me/{OWNER_USERNAME.replace('@', '')}")]
    ]

    await event.reply(welcome_text, buttons=buttons)

    # Log
    await log_to_channel(
        f"{e['zap']} **New User Started Bot**\n"
        f"👤 Name: [{user.first_name or 'Unknown'}](tg://user?id={uid})\n"
        f"🆔 ID: `{uid}`\n"
        f"📅 Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
    )

@client.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    e = EMOJIS
    help_text = f"""{e['info']} **BOT COMMANDS**

**User Commands:**
`/start` — Start the bot
`/help` — Show this message
`/history` — View your scan history
`/stats` — Bot usage statistics
`/myid` — Get your Telegram ID

**How to use:**
1. Send any `.apk` file
2. Wait for processing
3. Get full Firebase extraction report

**Extracted Data:**
• Firebase Realtime Database URL
• Firebase Project ID
• Auth Domain
• GCM Sender ID
• Storage Bucket
• Google API Key
• Mobile App ID
• OAuth Client IDs
• Package information
• Packer/Obfuscation detection

◆ **{'━'*10}** ◆
{e['zap']} Powered by {BRAND_NAME}"""

    await event.reply(help_text)

@client.on(events.NewMessage(pattern='/myid'))
async def myid_handler(event):
    user = await event.get_sender()
    e = EMOJIS
    text = f"""{e['id_card']} **YOUR PROFILE**

👤 Name: {user.first_name or 'N/A'}
🆔 User ID: `{user.id}`
📛 Username: @{user.username or 'N/A'}

◆ **{'━'*10}** ◆"""
    await event.reply(text)

@client.on(events.NewMessage(pattern='/stats'))
async def stats_handler(event):
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

@client.on(events.NewMessage(pattern='/history'))
async def history_handler(event):
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
    data = event.data.decode()
    uid = event.sender_id
    e = EMOJIS

    if data == "history":
        history = SCAN_HISTORY.get(uid, [])
        if not history:
            await event.edit(f"{e['folder']} **No scan history found.**\n\nSend an APK to start scanning!")
        else:
            text = f"{e['folder']} **YOUR SCAN HISTORY**\n\n"
            for i, item in enumerate(history[-10:], 1):
                text += f"{i}. `{item['filename']}` — {item['time']}\n"
            text += f"\n◆ **{'━'*10}** ◆"
            await event.edit(text)

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
        await event.edit(text)

    elif data == "scan_again":
        await event.edit(f"{e['fire']} **Send an APK to Start Scanning!**")

# ==================== APK HANDLER ====================
@client.on(events.NewMessage)
async def apk_handler(event):
    if not event.document:
        return

    # Check if it's an APK
    is_apk = False
    filename = "unknown.apk"

    if event.document.mime_type == 'application/vnd.android.package-archive':
        is_apk = True

    for attr in event.document.attributes:
        if hasattr(attr, 'file_name') and attr.file_name.endswith('.apk'):
            is_apk = True
            filename = attr.file_name
            break

    if not is_apk:
        return

    user = await event.get_sender()
    uid = user.id
    e = EMOJIS

    # Update stats
    USER_STATS[uid]["scans"] += 1
    USER_STATS[uid]["last_seen"] = datetime.now()
    BOT_STATS["total_scans"] += 1
    BOT_STATS["total_users"].add(uid)

    # Process one upload per user at a time — prevents floods and rate limits,
    # while other users' messages are handled instantly.
    queue = USER_QUEUE.get(uid)
    if queue is None:
        queue = USER_QUEUE[uid] = asyncio.Lock()

    if queue.locked():
        PENDING[uid] = PENDING.get(uid, 0) + 1

    async with queue:
        # This APK is now the active one — count what's still behind it.
        if PENDING.get(uid, 0) > 0:
            PENDING[uid] -= 1
        await _process_apk(event, user, uid, filename, e, PENDING.get(uid, 0))


async def _process_apk(event, user, uid, filename, e, pending=0):
    def queue_info():
        """ETA line shown while APKs are still queued behind this one."""
        if pending <= 0:
            return None
        eta = estimate_eta(uid, pending)
        return f"{e['timer']} Queue: `{pending}` APK(s) remaining | ETA: ~{eta:.0f}s"

    progress_msg = await _retry(event.reply, get_progress_text(filename, 1, queue_info()))
    tmp_dir = tempfile.mkdtemp()
    apk_path = os.path.join(tmp_dir, filename)
    last_edit = 0.0
    t0 = time.monotonic()

    try:
        # Step 1-2: Download
        last_edit = await _edit_progress(progress_msg, get_progress_text(filename, 2, queue_info()), last_edit)
        await event.download_media(file=apk_path)
        file_size = os.path.getsize(apk_path)

        # Step 3-4: Process (async — the event loop stays responsive)
        last_edit = await _edit_progress(progress_msg, get_progress_text(filename, 3, queue_info()), last_edit)
        last_edit = await _edit_progress(progress_msg, get_progress_text(filename, 4, queue_info()), last_edit)

        # Step 5: Extract — heavy CPU work runs in a thread pool,
        # so scanning 100 APKs never blocks the bot.
        last_edit = await _edit_progress(progress_msg, get_progress_text(filename, 5, queue_info()), last_edit)
        scanner = APKScanner(apk_path)
        results = await asyncio.to_thread(scanner.scan)

        # Timing: how long this APK took from start to results
        elapsed = time.monotonic() - t0
        results["scan_time"] = elapsed
        BOT_STATS["total_scan_time"] += elapsed

        # Step 6: Finalize
        await _edit_progress(progress_msg, get_progress_text(filename, 6, queue_info()), last_edit)

        # Format and send results
        result_text = get_scan_text(results, format_bytes(file_size))

        buttons = [
            [Button.inline(f"{e['folder']} View History", b"history"),
             Button.inline(f"{e['search']} Scan Another", b"scan_again")]
        ]

        await _safe_delete(progress_msg)
        await _retry(event.reply, result_text, buttons=buttons, link_preview=False)

        # Save to history
        SCAN_HISTORY[uid].append({
            "filename": filename,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "scan_time": results.get("scan_time"),
            "results": results
        })

        # Log to channel
        fb = results.get("firebase", {})
        api = results.get("api_credentials", {})
        log_text = (
            f"{e['fire']} **New APK Scanned**\n"
            f"👤 User: [{user.first_name or 'Unknown'}](tg://user?id={uid})\n"
            f"🆔 ID: `{uid}`\n"
            f"📦 File: `{filename}`\n"
            f"📊 Size: `{format_bytes(file_size)}`\n"
            f"📦 Package: `{results.get('package') or 'N/A'}`\n"
            f"🌐 DB URL: `{fb.get('db_url') or 'N/A'}`\n"
            f"🆔 Project: `{fb.get('project_id') or 'N/A'}`\n"
            f"🔑 API Key: `{api.get('google_api_key') or 'N/A'}`\n"
            f"📱 App ID: `{api.get('app_id') or 'N/A'}`\n"
            f"⏰ Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        await log_to_channel(log_text)

    except FloodWaitError as fw:
        # Telegram asked us to slow down — wait it out instead of crashing.
        print(f"[{BRAND_NAME}] Flood wait: {fw.seconds}s")
        await asyncio.sleep(fw.seconds + 1)
    except Exception as ex:
        await _safe_delete(progress_msg)
        await event.reply(
            f"{e['cross']} **EXTRACTION FAILED**\n\n"
            f"Error: `{str(ex)}`\n\n"
            f"Please try again with a valid APK file."
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ==================== MAIN ====================
async def main():
    print(f"[{BRAND_NAME}] Starting bot...")
    await client.start(bot_token=BOT_TOKEN)
    print(f"[{BRAND_NAME}] Bot is running!")
    print(f"[{BRAND_NAME}] Username: {BOT_USERNAME}")
    try:
        await client.run_until_disconnected()
    finally:
        await client.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print(f"\n[{BRAND_NAME}] Bot stopped.")
