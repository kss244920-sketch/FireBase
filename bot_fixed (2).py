"""
AnneBella Firebase Extractor Bot
Extracts Firebase configs & API credentials from APK files
Author: @AnneBella
Brand: Annebella Firebase
"""

import os
import sys
import re
import json
import zipfile
import tempfile
import shutil
import time
import hashlib
from datetime import datetime
from collections import defaultdict

from telethon import TelegramClient, events, Button
from telethon.tl.types import DocumentAttributeFilename

# ==================== CONFIG ====================
API_ID = 22602867
API_HASH = "7e2042dde2f4a8278cbe9d3bebae8ac5"
BOT_TOKEN = "8758625921:AAFLeP4IzKR-d_MVjYzrlEAs7GhVfgFDV30"
OWNER_ID = 8179406947
OWNER_USERNAME = "@AnneBella"
LOG_CHANNEL = -1003950236084
LOG_CHANNEL_URL = "https://t.me/firebaselogs"
BRAND_NAME = "Annebella Firebase"
BOT_USERNAME = "@AnnebellaFirebaseBot"

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
    "star": "⭐",
    "diamond": "💎",
    "link": "🔗",
}

# ==================== DATA STORAGE ====================
USER_STATS = defaultdict(lambda: {"scans": 0, "first_seen": None, "last_seen": None})
SCAN_HISTORY = defaultdict(list)  # user_id -> list of scan results
BOT_STATS = {"total_scans": 0, "total_users": set(), "start_time": datetime.now()}

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
            self._extract_firebase()
            self._extract_api_keys()
        except Exception as e:
            self.results["errors"].append(str(e))
        return self.results

    def _extract_manifest(self):
        """Extract package info from AndroidManifest.xml"""
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as z:
                # Try to find AndroidManifest.xml
                manifest_data = None
                for name in z.namelist():
                    if name.endswith('AndroidManifest.xml'):
                        manifest_data = z.read(name)
                        break

                if manifest_data:
                    # Simple regex extraction for package name
                    text = manifest_data.decode('utf-8', errors='ignore')
                    pkg_match = re.search(r'package=["\']([^"\']+)["\']', text)
                    if pkg_match:
                        self.results["package"] = pkg_match.group(1)

                    # Version info
                    ver_match = re.search(r'android:versionName=["\']([^"\']+)["\']', text)
                    if ver_match:
                        self.results["version"] = ver_match.group(1)

                    code_match = re.search(r'android:versionCode=["\']([^"\']+)["\']', text)
                    if code_match:
                        self.results["build_code"] = code_match.group(1)

                # Try to get app name from resources
                for name in z.namelist():
                    if 'resources.arsc' in name:
                        arsc_data = z.read(name)
                        arsc_text = arsc_data.decode('utf-8', errors='ignore')
                        # Look for app_name patterns
                        name_match = re.search(r'app_name.*?([A-Za-z][A-Za-z0-9_\s]{2,30})', arsc_text)
                        if name_match and not self.results["app_name"]:
                            self.results["app_name"] = name_match.group(1).strip()
                        break
        except Exception as e:
            self.results["errors"].append(f"Manifest error: {e}")

    def _scan_resources(self):
        """Scan all files in APK for Firebase patterns"""
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as z:
                self.all_text = ""
                for name in z.namelist():
                    if name.endswith(('.xml', '.json', '.txt', '.properties', '.smali', '.dex')):
                        try:
                            data = z.read(name)
                            text = data.decode('utf-8', errors='ignore')
                            self.all_text += text + "\n"
                        except:
                            pass
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

    def _extract_firebase(self):
        """Extract Firebase configuration"""
        text = getattr(self, 'all_text', '')

        # Firebase Database URL
        db_pattern = r'https://([a-zA-Z0-9_-]+)-default-rtdb\.firebaseio\.com'
        db_match = re.search(db_pattern, text)
        if db_match:
            project_id = db_match.group(1)
            self.results["firebase"]["db_url"] = f"https://{project_id}-default-rtdb.firebaseio.com"
            self.results["firebase"]["project_id"] = project_id
            self.results["firebase"]["auth_domain"] = f"{project_id}.firebaseapp.com"
        else:
            # Try alternative patterns
            alt_db = re.search(r'https://([a-zA-Z0-9_-]+)\.firebaseio\.com', text)
            if alt_db:
                pid = alt_db.group(1).replace('-default-rtdb', '')
                self.results["firebase"]["db_url"] = alt_db.group(0)
                self.results["firebase"]["project_id"] = pid
                self.results["firebase"]["auth_domain"] = f"{pid}.firebaseapp.com"

        # Google Services JSON pattern
        gservices = re.search(r'"project_info".*?"project_number"\s*:\s*"(\d+)"', text, re.DOTALL)
        if gservices:
            self.results["firebase"]["sender_id"] = gservices.group(1)
        else:
            # Try sender ID patterns
            sender_patterns = [
                r'gcm_defaultSenderId.*?([0-9]{10,20})',
                r'"sender_id"\s*:\s*"([0-9]{10,20})"',
                r'project_number.*?([0-9]{10,20})'
            ]
            for pattern in sender_patterns:
                match = re.search(pattern, text)
                if match:
                    self.results["firebase"]["sender_id"] = match.group(1)
                    break

        # Storage bucket
        storage_patterns = [
            r'([a-zA-Z0-9_-]+)\.appspot\.com',
            r'"storage_bucket"\s*:\s*"([^"]+)"',
            r'storageBucket.*?([a-zA-Z0-9_-]+\.appspot\.com)'
        ]
        for pattern in storage_patterns:
            match = re.search(pattern, text)
            if match:
                self.results["firebase"]["storage"] = match.group(1)
                break

        # If we have project_id but no storage, derive it
        if "project_id" in self.results["firebase"] and "storage" not in self.results["firebase"]:
            self.results["firebase"]["storage"] = f"{self.results['firebase']['project_id']}.appspot.com"

    def _extract_api_keys(self):
        """Extract API credentials"""
        text = getattr(self, 'all_text', '')

        # Google API Key
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
                    self.results["api_credentials"]["google_api_key"] = key
                    break

        # App ID / Mobile SDK
        app_id_patterns = [
            r'1:\d+:android:[a-f0-9]+',
            r'"mobilesdk_app_id"\s*:\s*"([^"]+)"',
            r'google_app_id.*?([0-9]+:[0-9]+:android:[a-f0-9]+)'
        ]
        for pattern in app_id_patterns:
            match = re.search(pattern, text)
            if match:
                app_id = match.group(0) if ':' in match.group(0) else match.group(1)
                self.results["api_credentials"]["app_id"] = app_id
                break

        # OAuth Client IDs
        oauth_pattern = r'([0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com)'
        oauth_matches = re.findall(oauth_pattern, text)
        if oauth_matches:
            self.results["api_credentials"]["oauth_clients"] = list(set(oauth_matches))


# ==================== BOT ====================
client = TelegramClient('annebella_firebase_bot', API_ID, API_HASH)

async def log_to_channel(text):
    """Send log to channel"""
    try:
        await client.send_message(LOG_CHANNEL, text, link_preview=False)
    except:
        pass

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

def get_progress_text(filename, step):
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

    text = f"""{e['chart']} **BOT STATISTICS**

📊 Total Scans: `{BOT_STATS['total_scans']}`
👥 Total Users: `{len(BOT_STATS['total_users'])}`
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
        text = f"""{e['chart']} **BOT STATISTICS**

📊 Total Scans: `{BOT_STATS['total_scans']}`
👥 Total Users: `{len(BOT_STATS['total_users'])}`
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

    # Send processing message
    progress_msg = await event.reply(get_progress_text(filename, 1))

    tmp_dir = tempfile.mkdtemp()
    apk_path = os.path.join(tmp_dir, filename)

    try:
        # Step 1-2: Download
        await progress_msg.edit(get_progress_text(filename, 2))
        await event.download_media(file=apk_path)
        file_size = os.path.getsize(apk_path)

        # Step 3-4: Process
        await progress_msg.edit(get_progress_text(filename, 3))
        await progress_msg.edit(get_progress_text(filename, 4))

        # Step 5: Extract
        await progress_msg.edit(get_progress_text(filename, 5))
        scanner = APKScanner(apk_path)
        results = scanner.scan()

        # Step 6: Finalize
        await progress_msg.edit(get_progress_text(filename, 6))
        await asyncio.sleep(0.5)

        # Format and send results
        result_text = get_scan_text(results, format_bytes(file_size))

        buttons = [
            [Button.inline(f"{e['folder']} View History", b"history"), 
             Button.inline(f"{e['search']} Scan Another", b"scan_again")]
        ]

        await progress_msg.delete()
        await event.reply(result_text, buttons=buttons, link_preview=False)

        # Save to history
        SCAN_HISTORY[uid].append({
            "filename": filename,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
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

    except Exception as ex:
        await progress_msg.delete()
        await event.reply(
            f"{e['cross']} **EXTRACTION FAILED**\n\n"
            f"Error: `{str(ex)}`\n\n"
            f"Please try again with a valid APK file."
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ==================== MAIN ====================
import asyncio

async def main():
    print(f"[{BRAND_NAME}] Starting bot...")
    await client.start(bot_token=BOT_TOKEN)
    print(f"[{BRAND_NAME}] Bot is running!")
    print(f"[{BRAND_NAME}] Username: {BOT_USERNAME}")
    await client.run_until_disconnected()

if __name__ == "__main__":
    client.loop.run_until_complete(main())
