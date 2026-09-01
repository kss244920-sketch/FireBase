import os
import re
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

# Cache of completed scans keyed by APK sha1 — identical re-scans skip parsing.
SCAN_CACHE = {}
MAX_CACHE_ENTRIES = 100

# Per-user lock so one user's many uploads are processed sequentially
# (prevents floods/rate limits) while other users stay responsive.
USER_QUEUE = {}
# Per-user count of APKs still waiting in the queue (used for ETA estimates).
PENDING = {}

# ==================== SPEED / SAFETY SETTINGS ====================
MAX_SCAN_FILE_SIZE = 2 * 1024 * 1024   # skip plaintext files larger than 2MB
MAX_AXML_SIZE = 8 * 1024 * 1024        # binary XML files up to 8MB
MAX_ARSC_SIZE = 32 * 1024 * 1024       # resources.arsc up to 32MB
MAX_DEX_SIZE = 96 * 1024 * 1024        # classes.dex up to 96MB
MAX_DEX_STRINGS = 200000               # cap strings decoded per dex file
MAX_POOL_STRINGS = 100000              # cap strings per binary string pool
MAX_CORPUS_STRINGS = 250000            # global cap for extracted string corpus
MAX_ARSC_CHUNKS = 50000                # safety cap for arsc chunk walker
PROGRESS_EDIT_INTERVAL = 0.8           # seconds between progress-message edits

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


def _axml_strings(data, cap=MAX_POOL_STRINGS):
    """Extract readable strings from a binary XML / ResStringPool string pool."""
    try:
        if len(data) < 28:
            return []
        ctype, hsize, _csize = struct.unpack_from('<HHI', data, 0)
        if ctype != 0x0001 or hsize < 28:
            return []
        string_count, _style_count, flags, strings_start, _styles_start = struct.unpack_from('<IIIII', data, 8)
        if not string_count or strings_start == 0 or strings_start > len(data):
            return []
        string_count = min(string_count, cap)
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


# ==================== DEX STRING TABLE PARSER ====================
class DexStrings:
    """Extract the string table from a .dex file (modern Android apps store
    Firebase URLs, API keys and package names here)."""
    # DEX header: magic(8) checksum(4) signature(20) file_size(4) header_size(4)
    # endian_tag(4) link_size(4) link_off(4) map_off(4) string_ids_size(4) string_ids_off(4)
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
                return []
            (magic, _checksum, _sig, _fsize, _hsize, _endsize,
             _link_size, _link_off, _map_off, string_ids_size, string_ids_off) = \
                struct.unpack_from(self.HEADER_FMT, self.data, 0)
            if magic[:4] != b'dex\n' or string_ids_size == 0 or string_ids_off == 0:
                return []
            string_ids_size = min(string_ids_size, cap)
            first_off = self._u(string_ids_off)
            if not first_off:
                return []
            count = 0
            max_pos = min(self._u(string_ids_off + (string_ids_size - 1) * 4), len(self.data) - 1) if string_ids_size else 0
            for i in range(string_ids_size):
                if max_pos and i > 0:
                    # Dex strings often hold NUL-padding after a string; if a
                    # string_data's address sits on the previous string's tail,
                    # reading it is still safe (ULEB will just decode zeros).
                    pass
                data_off = self._u(string_ids_off + i * 4)
                if not data_off or data_off >= len(self.data):
                    continue
                pos = data_off
                try:
                    b = self.data[pos]
                    pos += 1
                    if b & 0x80:
                        b2 = self.data[pos]
                        pos += 1
                        size = ((b & 0x7F) << 8) | b2
                    else:
                        size = b
                except IndexError:
                    continue
                if size <= 0 or size > 0xFFFF:
                    continue
                end = self.data.find(b'\x00', pos, min(pos + size * 4 + 1, len(self.data)))
                if end == -1:
                    continue
                try:
                    s = self.data[pos:end].decode('utf-8', errors='ignore')
                except Exception:
                    continue
                if s:
                    count += 1
                    yield s
            if count == 0:
                return []
        except Exception:
            return []


# ==================== ANDROID RESOURCE TABLE (resources.arsc) PARSER ====================
class ArscStrings:
    """Walk resources.arsc to build an exact resource key -> value map.

    This finds firebase_* resources even though their names and values live in
    separate binary chunks with no plaintext 'package=' marker anywhere."""

    _KEY = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_.]*$')

    def __init__(self, data):
        self.data = data

    def _u(self, off, fmt='<I'):
        try:
            return struct.unpack_from(fmt, self.data, off)[0]
        except struct.error:
            return 0

    def get_pairs(self, cap=MAX_ARSC_CHUNKS):
        pairs = []
        try:
            d = self.data
            n = len(d)
            off = 0
            if n < 12:
                return pairs
            _hsize = struct.unpack_from('<H', d, 0)[0]
            # Android: ResTable header is 12 bytes, ResTable_package is 288.
            # We just skip whatever header size is declared so chunks align.
            hsize = struct.unpack_from('<H', d, 2)[0]
            off = hsize if hsize >= 12 else 12
            while off + 8 <= n and len(pairs) < cap:
                ctype, _hsize, csize = struct.unpack_from('<HHI', d, off)
                if csize < 8 or off + csize > n:
                    break
                if ctype == 0x0001:  # ResStringPoolHeader — decode the whole chunk
                    string_count = self._u(off + 8)
                    if string_count:
                        pairs.extend(_axml_strings(d[off:off + csize], string_count))
                    off += csize
                else:
                    off += csize
        except Exception:
            pass
        return pairs


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
                        self._extract_google_services(z.read(google_services_entry))
                    except Exception:
                        pass

                # 3. Android Resource Table (ARSC)
                if arsc_entry:
                    try:
                        info = z.getinfo(arsc_entry)
                        if 0 < info.file_size <= MAX_ARSC_SIZE:
                            arsc_strs = ArscStrings(z.read(arsc_entry)).get_pairs()
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
                    try:
                        info = z.getinfo(dex_name)
                        if 0 < info.file_size <= MAX_DEX_SIZE:
                            data = z.read(dex_name)
                            # Fast raw-byte pattern sweep
                            for pat, _ in self.BYTE_PRESCAN_PATTERNS:
                                for m in pat.finditer(data):
                                    self._extract_all_patterns(m.group(0).decode('utf-8', errors='ignore'))
                            # Deep DEX string pool walker
                            for s in DexStrings(data).get_strings():
                                self._extract_all_patterns(s)
                    except Exception:
                        pass

                # 5. Plaintext configs, smali & JSON files
                for code_name in other_code_entries:
                    try:
                        raw = z.read(code_name)
                        text = raw.decode('utf-8', errors='ignore')
                        self._extract_all_patterns(text)
                    except Exception:
                        pass

                # 6. Native shared libraries (.so ELF string scraping)
                for so_name in native_entries:
                    try:
                        info = z.getinfo(so_name)
                        if 0 < info.file_size <= 16 * 1024 * 1024:
                            raw = z.read(so_name)
                            for pat, _ in self.BYTE_PRESCAN_PATTERNS:
                                for m in pat.finditer(raw):
                                    self._extract_all_patterns(m.group(0).decode('utf-8', errors='ignore'))
                            for s in re.findall(rb'[\x20-\x7E]{6,}', raw):
                                try:
                                    self._extract_all_patterns(s.decode('utf-8', errors='ignore'))
                                except Exception:
                                    pass
                    except Exception:
                        pass

                # 7. Hidden Asset, Droppers & Deep Deobfuscation (Base64 recursive, XOR, Hex, Inversion)
                for name in (asset_entries + other_code_entries):
                    try:
                        raw = z.read(name)
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
            manifest_data = None
            if z.getinfo(manifest_name).file_size <= MAX_AXML_SIZE:
                manifest_data = z.read(manifest_name)

            if not manifest_data:
                return

            strings = _axml_strings(manifest_data)
            if strings:
                for s in strings:
                    self._extract_all_patterns(s)
                # App label
                if not self.results.get("app_name"):
                    for s in strings:
                        if 2 <= len(s) <= 40 and re.match(r'^[\w][\w\s&.\-()]*$', s) and \
                                not re.fullmatch(r'[\w.]+', s) and ' ' not in s[:3]:
                            self.results["app_name"] = s
                            break
                # Package name
                for s in strings:
                    if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*){2,}', s) and \
                            'firebase' not in s.lower():
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
                        info = z.getinfo(name)
                        if 0 < info.file_size <= 16 * 1024 * 1024:
                            raw = z.read(name)

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
                    info = z.getinfo(name)
                    if 0 < info.file_size <= 12 * 1024 * 1024:
                        raw = z.read(name)
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
                    raw = z.read(name)

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
        fb = self.results["firebase"]

        # Firebase RTDB Database URLs
        if not fb.get("project_id") or not fb.get("db_url"):
            for pat in [
                re.compile(r'https://([a-zA-Z0-9_-]+)-default-rtdb\.(?:([a-z0-9-]+)\.)?firebasedatabase\.app', re.I),
                re.compile(r'https://([a-zA-Z0-9_-]+)\.(?:([a-z0-9-]+)\.)?firebasedatabase\.app', re.I),
                re.compile(r'https://([a-zA-Z0-9_-]+)-default-rtdb\.firebaseio\.com', re.I),
                re.compile(r'https://([a-zA-Z0-9_-]+)\.firebaseio\.com', re.I),
                re.compile(r'https://firestore\.googleapis\.com/v1/projects/([a-zA-Z0-9_-]+)', re.I)
            ]:
                m = pat.search(text)
                if m:
                    fb["db_url"] = m.group(0)
                    fb["project_id"] = m.group(1)
                    fb["auth_domain"] = f"{m.group(1)}.firebaseapp.com"
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
                match = re.search(pattern, text, re.DOTALL if '"project_info"' in pattern else 0)
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

        if not fb.get("project_id"):
            pid = project_info.get("project_id")
            if pid:
                fb["project_id"] = pid
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
                ('libprotect', "Custom Protect"),
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

def probe_firebase_database(db_url: str, auth_key: str = None, timeout: float = 3.5) -> dict:
    """Probes a Firebase Realtime Database for online/offline/total devices and access status."""
    if not db_url or "firebase" not in db_url:
        return {}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    clean_url = db_url.rstrip("/")
    if clean_url.endswith(".json"):
        clean_url = clean_url[:-5]

    results = {
        "status": "Unknown",
        "accessible": False,
        "online": 0,
        "offline": 0,
        "total": 0,
        "nodes": []
    }

    def _query(endpoint: str, use_auth: bool = False):
        url = f"{clean_url}/{endpoint}.json"
        if use_auth and auth_key:
            url += f"?auth={auth_key}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)

    # 1. First probe common device roots
    device_endpoints = ["clients", "devices", "victim", "users", "data"]
    for ep in device_endpoints:
        for use_auth in ([False, True] if auth_key else [False]):
            try:
                with _query(ep, use_auth=use_auth) as resp:
                    if resp.status == 200:
                        raw = resp.read().decode("utf-8", errors="ignore")
                        if raw and raw != "null":
                            data = json.loads(raw)
                            if isinstance(data, dict) and data:
                                online = 0
                                offline = 0
                                for k, v in data.items():
                                    if isinstance(v, dict):
                                        st = v.get("status")
                                        if st is None: st = v.get("isOnline")
                                        if st is None: st = v.get("online")
                                        if st is None: st = v.get("state")
                                        if st is None: st = v.get("connected")
                                        if st is True or st == 1 or str(st).lower() in ("online", "true", "active", "connected", "1"):
                                            online += 1
                                        else:
                                            offline += 1
                                    else:
                                        offline += 1
                                results["accessible"] = True
                                results["status"] = "🟢 Open (Accessible)" if not use_auth else "🔑 Auth Verified"
                                results["online"] = online
                                results["offline"] = offline
                                results["total"] = len(data)
                                return results
            except urllib.error.HTTPError as he:
                if he.code in (401, 403):
                    results["status"] = "🔒 Protected (Auth Required)"
                elif he.code == 404:
                    results["status"] = "🔴 Not Found (404)"
            except Exception:
                pass

    # 2. Check root shallow if no device endpoints returned devices
    try:
        url = f"{clean_url}/.json?shallow=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8", errors="ignore")
                if raw and raw != "null":
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        results["accessible"] = True
                        results["status"] = "🟢 Open (0 Devices / Inactive)"
                        results["nodes"] = list(data.keys())[:6]
                        return results
    except urllib.error.HTTPError as he:
        if he.code in (401, 403):
            results["status"] = "🔒 Protected (Auth Required)"
            return results
    except Exception:
        pass

    if results["status"] == "Unknown":
        results["status"] = "⚪ Inactive / Empty"
    return results

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

    # Device Statistics (Online, Offline, Total)
    dev_stats = results.get("device_stats")
    if dev_stats:
        lines.append(f"📊 **Device Statistics**")
        if dev_stats.get("accessible") and dev_stats.get("total", 0) > 0:
            lines.append(f"🟢 Online:     `{dev_stats.get('online', 0)}`")
            lines.append(f"🔴 Offline:    `{dev_stats.get('offline', 0)}`")
            lines.append(f"📱 Total:      `{dev_stats.get('total', 0)}`")
        elif dev_stats.get("accessible"):
            lines.append(f"📱 Total:      `0 devices`")
        lines.append(f"🛡️ DB Access:  {dev_stats.get('status', 'Unknown')}")
        if dev_stats.get("nodes"):
            nodes_str = ", ".join(f"`/{n}`" for n in dev_stats["nodes"])
            lines.append(f"📁 Root Nodes: {nodes_str}")
        lines.append("")

    # Telegram C2 Channel (if detected)
    tg = results.get("telegram_c2", {})
    if tg.get("bot_token") or tg.get("chat_id"):
        lines.append(f"🤖 **Telegram C2 Infrastructure**")
        if tg.get("bot_token"):
            lines.append(f"🔑 Bot Token: `{tg['bot_token']}`")
        if tg.get("chat_id"):
            lines.append(f"📢 Chat ID:   `{tg['chat_id']}`")
        lines.append("")

    # Webhooks & C2 Endpoints (if detected)
    webhooks = results.get("webhooks", [])
    c2s = results.get("c2_endpoints", [])
    if webhooks or c2s:
        lines.append(f"🌐 **Webhooks & C2 Endpoints**")
        for wh in webhooks[:3]:
            lines.append(f"💬 Webhook: `{wh}`")
        for c2 in c2s[:3]:
            lines.append(f"🔗 C2 Gate: `{c2}`")
        lines.append("")

    # Target Forwarding Phone Numbers (if detected)
    phones = results.get("forward_phones", [])
    if phones:
        lines.append(f"📞 **Target Forwarding Numbers**")
        for ph in phones[:4]:
            lines.append(f"📱 Phone: `{ph}`")
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

        tg_c2 = results.get("telegram_c2", {})
        tg_line = f"🤖 TG Bot: `{tg_c2.get('bot_token')}`\n" if tg_c2.get("bot_token") else ""
        if tg_c2.get("chat_id"):
            tg_line += f"📢 TG Chat: `{tg_c2.get('chat_id')}`\n"

        log_text = (
            f"{e['fire']} **New APK Scanned**\n"
            f"👤 User: [{user.first_name or 'Unknown'}](tg://user?id={uid})\n"
            f"🆔 ID: `{uid}`\n"
            f"📦 File: `{filename}`\n"
            f"📊 Size: `{format_bytes(file_size)}`\n"
            f"📦 Package: `{results.get('package') or 'N/A'}`\n"
            f"🌐 DB URL: `{fb.get('db_url') or 'N/A'}`\n"
            f"{dev_line}"
            f"{tg_line}"
            f"🆔 Project: `{fb.get('project_id') or 'N/A'}`\n"
            f"🔑 API Key: `{api.get('google_api_key') or 'N/A'}`\n"
            f"📱 App ID: `{api.get('app_id') or 'N/A'}`\n"
            f"⏰ Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        await log_to_channel(log_text)

        owner_text = (
            f"{e['fire']} **APK SCANNED**\n"
            f"👤 User: [{user.first_name or 'Unknown'}](tg://user?id={uid})\n"
            f"🆔 ID: `{uid}`\n"
            f"📛 Username: @{user.username or 'N/A'}\n"
            f"\n"
            f"{result_text}"
        )
        await log_to_owner(owner_text)
    except Exception:
        pass


async def _process_apk(event, user, uid, filename, e, pending=0):
    t0 = time.monotonic()
    queue_text = f" | {e['timer']} Queue: `{pending}`" if pending > 0 else ""

    # Instant progress notification (single message, no edit throttling)
    progress_msg = await _retry(
        event.reply,
        f"{e['zap']} **Processing:** `{filename}`{queue_text}\n\n{e['chart']} Downloading & analyzing APK...",
        link_preview=False
    )
    tmp_dir = tempfile.mkdtemp()
    apk_path = os.path.join(tmp_dir, filename)

    try:
        # 1. Download at maximum speed
        await event.download_media(file=apk_path)
        file_size = os.path.getsize(apk_path)

        # 2. Fast multi-pass / single-stream scan in thread
        scanner = APKScanner(apk_path)
        results = await asyncio.to_thread(scanner.scan)

        # 3. Live probe Firebase database for device counts & access status
        fb = results.get("firebase", {})
        api = results.get("api_credentials", {})
        if fb.get("db_url"):
            dev_stats = await asyncio.to_thread(
                probe_firebase_database,
                fb["db_url"],
                api.get("google_api_key")
            )
            results["device_stats"] = dev_stats

        # 4. Total timing
        elapsed = time.monotonic() - t0
        results["scan_time"] = elapsed
        BOT_STATS["total_scan_time"] += elapsed

        # 5. Format & instantly edit progress message with results (no delete lag)
        result_text = get_scan_text(results, format_bytes(file_size))
        buttons = [
            [Button.inline(f"{e['folder']} View History", b"history"),
             Button.inline(f"{e['search']} Scan Another", b"scan_again")]
        ]
        await _retry(progress_msg.edit, result_text, buttons=buttons, link_preview=False)

        # 6. Save history
        SCAN_HISTORY[uid].append({
            "filename": filename,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "scan_time": results.get("scan_time"),
            "results": results
        })

        # 7. Background async logging (does not delay user response)
        asyncio.create_task(_send_background_logs(user, uid, filename, file_size, results, result_text, e))

    except FloodWaitError as fw:
        print(f"[{BRAND_NAME}] Flood wait: {fw.seconds}s")
        await asyncio.sleep(fw.seconds + 1)
    except Exception as ex:
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


# ==================== MAIN ====================
async def main():
    print(f"[{BRAND_NAME}] Starting bot...", flush=True)
    await client.start(bot_token=BOT_TOKEN)
    print(f"[{BRAND_NAME}] Bot is running!", flush=True)
    print(f"[{BRAND_NAME}] Username: {BOT_USERNAME}", flush=True)

    # Minimal health endpoint so Railway/Replit see the process as healthy.
    if os.environ.get("PORT"):
        port = int(os.environ.get("PORT", "8080"))
        asyncio.create_task(_health_server(port))

    try:
        await client.run_until_disconnected()
    finally:
        await client.disconnect()


async def _health_server(port):
    """Serve a tiny 'ok' HTTP reply so Railway's health checks pass."""
    try:
        import asyncio
        server = await asyncio.start_server(_health_handle, '0.0.0.0', port)
        print(f"[{BRAND_NAME}] Health server on port {port}", flush=True)
        await server.serve_forever()
    except Exception as e:
        print(f"[{BRAND_NAME}] Health server error: {e}", flush=True)


async def _health_handle(reader, writer):
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    try:
        await writer.drain()
    except Exception:
        pass
    writer.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print(f"\n[{BRAND_NAME}] Bot stopped.")
