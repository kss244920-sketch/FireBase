#!/usr/bin/env python3
"""
Hyper-Realistic Telegram Motion Graphics Showcase Video Generator (Full HD 1080p 60 FPS)
Designed specifically for @Kkftinbot matching Telegram's official promotional video style:
- 1920x1080 Full HD 16:9 widescreen layout
- 60 FPS ultra-fluid buttery motion graphics
- Vibrant Telegram Sky Blue canvas (#0f88eb gradient with soft ambient glow)
- Left column: Bold kinetic typography (Lato-Black & Lato-Regular) with animated watermarks
- Right column: Realistic white smartphone mockup with drop shadow and floating levitation
- Authentic Telegram Dark Mode chat interface (#0e1621, #17212b, #2b5278, #182533)
- Real-time animated progress bar (10% -> 50% -> 85% -> 100%)
- Deep Firebase scan report with live database metrics
- EXACT NATIVE COLORED BUTTONS sampled directly from user screenshot (Teal #2b6b84, Red #914236, Green #377531)
- Authentic touch pointer disc with cubic spline trajectory, tap contraction, and expanding ripple rings
- Live Database Probe Toast popup
- Exclusive Admin Suite transition and APK Auto-Archival alert to channel -1003776813052
- Synchronized electronic soundtrack with smooth end fadeout
"""

import os
import sys
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
FPS = 60
DURATION = 28.0
TOTAL_FRAMES = int(DURATION * FPS) # 1680 frames

FRAMES_DIR = "/tmp/promo_1080p_60fps_frames"
AUDIO_FILE = "/tmp/showcase_audio_28s.aac"
OUTPUT_VIDEO = "/home/piyush/Desktop/Firebase_Bot_Showcase.mp4"

# Exact colors from Telegram and User Screenshot
BG_CHAT = (14, 22, 33)           # #0e1621
BAR_HEADER = (23, 33, 43)        # #17212b
USER_BUBBLE = (43, 82, 120)      # #2b5278
BOT_BUBBLE = (24, 37, 51)        # #182533
BTN_TEAL = (43, 107, 132)        # #2b6b84 (Scanner Hub, Panels, Support)
BTN_RED = (145, 66, 54)          # #914236 (Admin Suite, Back)
BTN_GREEN = (55, 117, 49)        # #377531 (Export Hub)
TEXT_WHITE = (255, 255, 255)
TEXT_MUTED = (165, 200, 235)
ACCENT_BLUE = (80, 175, 255)
ACCENT_GREEN = (75, 215, 130)
ACCENT_ORANGE = (255, 150, 45)

# Fonts
FONT_NUM = ImageFont.truetype("/usr/share/fonts/truetype/lato/Lato-Black.ttf", 160)
FONT_TITLE = ImageFont.truetype("/usr/share/fonts/truetype/lato/Lato-Black.ttf", 76)
FONT_SUB = ImageFont.truetype("/usr/share/fonts/truetype/lato/Lato-Regular.ttf", 28)
FONT_CHAT_BOLD = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 18)
FONT_CHAT_REG = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 15)
FONT_CHAT_SMALL = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 13)
FONT_CODE = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 14)
FONT_BTN = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 16)
FONT_EMOJI_BASE = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)

EMOJI_CACHE = {}

def get_emoji(char, size=18):
    key = (char, size)
    if key in EMOJI_CACHE:
        return EMOJI_CACHE[key]
    c = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.text((10, 10), char, font=FONT_EMOJI_BASE, embedded_color=True)
    bbox = c.getbbox()
    if bbox:
        c = c.crop(bbox)
    c = c.resize((size, size), Image.Resampling.LANCZOS)
    EMOJI_CACHE[key] = c
    return c

def ease_out_cubic(x):
    return 1 - pow(1 - max(0.0, min(1.0, x)), 3)

def ease_in_out(x):
    clamped = max(0.0, min(1.0, x))
    return -(math.cos(math.pi * clamped) - 1) / 2

def draw_styled_button(screen, s_draw, bx, by, bw, bh, bg_col, em_char, text, is_pressed=False, has_arrow=False):
    fill_col = tuple(min(255, c + 35) for c in bg_col) if is_pressed else bg_col
    border_col = tuple(min(255, c + 45) for c in bg_col)
    s_draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=10, fill=fill_col, outline=border_col, width=1)
    
    em_icon = get_emoji(em_char, 18) if em_char else None
    em_w = 26 if em_icon else 0
    tb = s_draw.textbbox((0, 0), text, font=FONT_BTN)
    tw = tb[2] - tb[0]
    total_w = em_w + tw
    start_x = bx + (bw - total_w) // 2
    start_y = by + (bh - FONT_BTN.size) // 2
    if em_icon:
        screen.paste(em_icon, (start_x, by + (bh - 18) // 2), em_icon)
    s_draw.text((start_x + em_w, start_y), text, fill=(255, 255, 255), font=FONT_BTN)
    if has_arrow:
        ax = bx + bw - 18
        ay = by + 10
        s_draw.line([(ax, ay + 8), (ax + 8, ay)], fill=(210, 230, 250), width=2)
        s_draw.line([(ax + 3, ay), (ax + 8, ay), (ax + 8, ay + 5)], fill=(210, 230, 250), width=2)

def render_frame_worker(frame_idx):
    sec = frame_idx / float(FPS)

    canvas = Image.new("RGBA", (W, H), (15, 136, 235, 255))
    draw = ImageDraw.Draw(canvas)

    # 1. Background Gradient (Telegram Sky Blue)
    for y in range(H):
        factor = y / float(H)
        r = int(14 * (1 - factor) + 10 * factor)
        g = int(142 * (1 - factor) + 116 * factor)
        b = int(242 * (1 - factor) + 214 * factor)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Ambient Pulsing Glow behind Smartphone
    pulse = math.sin(sec * 1.5) * 20
    glow = Image.new("RGBA", (850, 1150), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([50 - int(pulse // 2), 100 - int(pulse // 2), 800 + int(pulse // 2), 1000 + int(pulse // 2)], fill=(255, 255, 255, 34))
    glow = glow.filter(ImageFilter.GaussianBlur(85))
    canvas.paste(glow, (1150, 0), glow)

    # 2. Scene Identification & Left Kinetic Typography
    # Scene 1: 0.0s - 5.5s (APK Drop & Progress)
    # Scene 2: 5.5s - 11.5s (Report & Colored Buttons)
    # Scene 3: 11.5s - 17.5s (Live DB Probe)
    # Scene 4: 17.5s - 23.0s (Admin Suite & Archive)
    # Scene 5: 23.0s - 28.0s (Outro & 24/7 Render Cloud)
    
    if sec < 5.5:
        scene_num = "01"
        scene_title = "Instant APK\nIntelligence"
        scene_sub = "Drop any Android .apk file into @Kkftinbot.\nThe engine automatically launches parallel\ndecompilation and bytecode analysis."
        t_enter = min(1.0, sec / 0.8)
    elif sec < 11.5:
        scene_num = "02"
        scene_title = "Deep Firebase\nExtraction"
        scene_sub = "Extracts Firebase project URLs, API keys,\nFCM credentials, and presents native\ncolored interactive action hubs."
        t_enter = min(1.0, (sec - 5.5) / 0.8)
    elif sec < 17.5:
        scene_num = "03"
        scene_title = "Live Database\nValidation"
        scene_sub = "Instant automated probe validates read/write\npermissions directly against Firebase cloud\nwith active live node statistics."
        t_enter = min(1.0, (sec - 11.5) / 0.8)
    elif sec < 23.0:
        scene_num = "04"
        scene_title = "Exclusive\nAdmin Suite"
        scene_sub = "Private admin-only controls with live telemetry,\nbroadcast tools, and auto-archival of all APKs\nto private channel -1003776813052."
        t_enter = min(1.0, (sec - 17.5) / 0.8)
    else:
        scene_num = "05"
        scene_title = "24/7 Live\nCloud Engine"
        scene_sub = "Hosted on Render Free Cloud Tier with\ncontinuous zero-downtime auto-healer.\nAvailable right now on Telegram!"
        t_enter = min(1.0, (sec - 23.0) / 0.8)

    # Smooth slide-in for title
    slide_offset = int((1.0 - ease_out_cubic(t_enter)) * 40)
    alpha_text = int(ease_out_cubic(t_enter) * 255)

    # Left Column Rendering
    draw.text((120, 840), scene_num, fill=(255, 255, 255, 55), font=FONT_NUM)
    draw.text((120, 360 - slide_offset), scene_title, fill=(255, 255, 255, alpha_text), font=FONT_TITLE)
    draw.text((120, 560 - slide_offset // 2), scene_sub, fill=(230, 242, 255, int(alpha_text * 0.85)), font=FONT_SUB)

    # Outro specific badge
    if sec >= 23.0:
        badge_y = 700 - slide_offset // 2
        draw.rounded_rectangle([120, badge_y, 440, badge_y + 44], radius=22, fill=(255, 255, 255, 45), outline=(255, 255, 255, 120), width=1)
        draw.text((150, badge_y + 10), "Telegram: @Kkftinbot", fill=(255, 255, 255), font=FONT_CHAT_BOLD)

    # 3. Right Column: Smartphone Mockup
    phone_w, phone_h = 510, 960
    phone_x = 1270
    
    # Floating levitation physics
    float_y = int(math.sin(sec * 1.6) * 6)
    phone_y = 60 + float_y

    # Smooth intro slide-in for phone
    if sec < 1.0:
        p_intro = ease_out_cubic(sec / 1.0)
        phone_y += int((1.0 - p_intro) * 120)

    # Drop Shadow
    shadow = Image.new("RGBA", (phone_w + 80, phone_h + 80), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle([40, 40, phone_w + 40, phone_h + 40], radius=54, fill=(0, 0, 0, 95))
    shadow = shadow.filter(ImageFilter.GaussianBlur(32))
    canvas.paste(shadow, (phone_x - 30, phone_y - 15), shadow)

    # White Bezel (Matches Telegram showcase reference)
    draw.rounded_rectangle([phone_x, phone_y, phone_x + phone_w, phone_y + phone_h], radius=52, fill=(248, 250, 252), outline=(225, 230, 235), width=3)

    # Top Speaker Pill & Selfie Camera Punch-hole
    draw.rounded_rectangle([phone_x + (phone_w - 74) // 2, phone_y + 14, phone_x + (phone_w + 74) // 2, phone_y + 20], radius=3, fill=(195, 202, 210))
    draw.ellipse([phone_x + phone_w // 2 + 65, phone_y + 13, phone_x + phone_w // 2 + 73, phone_y + 21], fill=(160, 170, 180))

    # Phone Screen Dimensions
    screen_w, screen_h = 474, 888
    screen_x, screen_y = phone_x + 18, phone_y + 36

    screen = Image.new("RGBA", (screen_w, screen_h), BG_CHAT)
    s_draw = ImageDraw.Draw(screen)

    # Android Status Bar
    s_draw.text((24, 8), "9:41", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.rounded_rectangle([screen_w - 44, 11, screen_w - 18, 23], radius=3, outline=(255, 255, 255), width=2)
    s_draw.rectangle([screen_w - 41, 14, screen_w - 24, 20], fill=(255, 255, 255))
    s_draw.rectangle([screen_w - 17, 14, screen_w - 15, 20], fill=(255, 255, 255))

    # Telegram Chat App Header Bar (#17212b)
    head_y, head_h = 32, 60
    s_draw.rectangle([0, head_y, screen_w, head_y + head_h], fill=BAR_HEADER)
    # Back Arrow
    s_draw.polygon([(22, head_y + 30), (32, head_y + 20), (32, head_y + 40)], fill=(120, 150, 180))
    # Bot Avatar Circle
    s_draw.ellipse([46, head_y + 10, 86, head_y + 50], fill=(255, 130, 20))
    em_flame = get_emoji("🔥", 26)
    screen.paste(em_flame, (53, head_y + 17), em_flame)
    # Header title & subtitle
    s_draw.text((98, head_y + 10), "Firebase Extractor Bot", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((98, head_y + 32), "bot • @Kkftinbot", fill=ACCENT_BLUE, font=FONT_CHAT_REG)
    # 3 dots
    for dy in [18, 27, 36]:
        s_draw.ellipse([screen_w - 30, head_y + dy, screen_w - 26, head_y + dy + 4], fill=(160, 185, 210))

    # User Message: Uploaded APK File Bubble (#2b5278)
    ub_y, ub_w, ub_h = head_y + 76, 320, 72
    ub_x = screen_w - ub_w - 16
    s_draw.rounded_rectangle([ub_x, ub_y, ub_x + ub_w, ub_y + ub_h], radius=16, fill=USER_BUBBLE)
    s_draw.ellipse([ub_x + 12, ub_y + 12, ub_x + 60, ub_y + 60], fill=(65, 145, 215))
    s_draw.text((ub_x + 19, ub_y + 24), "APK", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((ub_x + 72, ub_y + 16), "sexchat.apk", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((ub_x + 72, ub_y + 40), "5.1 MB • 12:00 PM", fill=TEXT_MUTED, font=FONT_CHAT_SMALL)
    
    # Double checkmarks (animated)
    if sec >= 0.8:
        cx, cy = ub_x + ub_w - 40, ub_y + 45
        s_draw.line([(cx, cy), (cx + 4, cy + 5), (cx + 10, cy - 4)], fill=ACCENT_GREEN, width=2)
        s_draw.line([(cx + 6, cy), (cx + 10, cy + 5), (cx + 16, cy - 4)], fill=ACCENT_GREEN, width=2)
    else:
        cx, cy = ub_x + ub_w - 30, ub_y + 45
        s_draw.line([(cx, cy), (cx + 4, cy + 5), (cx + 10, cy - 4)], fill=TEXT_MUTED, width=2)

    # SCENE 1 (1.0s to 5.4s): Real-time Scanning Progress Bar
    if 1.0 <= sec < 5.4:
        pb_y = ub_y + 88
        pb_w = 442
        pb_h = 100
        pb_x = 16
        s_draw.rounded_rectangle([pb_x, pb_y, pb_x + pb_w, pb_y + pb_h], radius=16, fill=BOT_BUBBLE, outline=(36, 54, 74), width=1)
        
        # Progress calculations
        # 1.0 to 2.2: 10% -> 45%
        # 2.2 to 3.8: 45% -> 85%
        # 3.8 to 5.0: 85% -> 100%
        # 5.0 to 5.4: 100%
        if sec < 2.2:
            p = 0.10 + (sec - 1.0) / 1.2 * 0.35
            step_desc = "Decompiling Dex & Bytecode (Parallel)..."
        elif sec < 3.8:
            p = 0.45 + (sec - 2.2) / 1.6 * 0.40
            step_desc = "Extracting AndroidManifest.xml & Strings..."
        elif sec < 5.0:
            p = 0.85 + (sec - 3.8) / 1.2 * 0.15
            step_desc = "Probing Firebase Realtime DB Endpoints..."
        else:
            p = 1.0
            step_desc = "Scan Complete! Building Action Hubs..."
            
        p = min(1.0, max(0.10, p))

        em_bolt = get_emoji("⚡", 20)
        screen.paste(em_bolt, (pb_x + 16, pb_y + 14), em_bolt)
        s_draw.text((pb_x + 44, pb_y + 14), "Analyzing APK Security...", fill=ACCENT_BLUE, font=FONT_CHAT_BOLD)

        # Background track
        bar_x = pb_x + 16
        bar_y = pb_y + 44
        bar_w = pb_w - 32
        bar_h = 12
        s_draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=6, fill=(35, 52, 72))
        
        # Fill bar
        fill_w = int(bar_w * p)
        if fill_w > 0:
            s_draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=6, fill=(40, 175, 255))
            # Glowing tip
            s_draw.ellipse([bar_x + fill_w - 6, bar_y - 2, bar_x + fill_w + 6, bar_y + bar_h + 2], fill=(120, 215, 255))

        pct_label = f"{int(p * 100)}% • {step_desc}"
        s_draw.text((bar_x, pb_y + 68), pct_label, fill=(180, 210, 240), font=FONT_CHAT_SMALL)

    # SCENE 2 & 3: Scan Report & EXACT Colored Buttons (5.4s to 17.0s)
    elif 5.4 <= sec < 17.0:
        rep_y, rep_w, rep_h = ub_y + 88, 442, 450
        rep_x = 16
        s_draw.rounded_rectangle([rep_x, rep_y, rep_x + rep_w, rep_y + rep_h], radius=18, fill=BOT_BUBBLE, outline=(36, 54, 74), width=1)

        # Header
        em_rep = get_emoji("🔥", 22)
        screen.paste(em_rep, (rep_x + 16, rep_y + 14), em_rep)
        s_draw.text((rep_x + 46, rep_y + 14), "FIREBASE SCAN REPORT", fill=ACCENT_ORANGE, font=FONT_CHAT_BOLD)
        s_draw.line([(rep_x + 16, rep_y + 42), (rep_x + rep_w - 16, rep_y + 42)], fill=(40, 58, 80))

        # Fields
        fields = [
            ("📦", "Package: com.target.sexchat", (230, 240, 250)),
            ("🌐", "DB: kkftin-prod.firebaseio.com", ACCENT_BLUE),
            ("🔑", "Key: AIzaSyBg98X_01qR92x4L0", (210, 225, 240)),
            ("📡", "FCM: AAAA9xK201_9QzL0w817", (210, 225, 240)),
            ("👥", "Live Nodes: 1,420 Connected", ACCENT_GREEN),
            ("🔓", "Status: OPEN / VULNERABLE DB!", (255, 110, 110))
        ]
        fy = rep_y + 50
        for em_char, ftext, fcolor in fields:
            em_icon = get_emoji(em_char, 18)
            screen.paste(em_icon, (rep_x + 16, fy + 2), em_icon)
            s_draw.text((rep_x + 44, fy), ftext, fill=fcolor, font=FONT_CHAT_REG)
            fy += 26

        # Buttons
        by = rep_y + 215
        bh = 44
        half_w = (rep_w - 38) // 2
        full_w = rep_w - 32

        # Tap on Scanner Hub: 11.8s to 12.4s
        is_scanner_pressed = (11.8 <= sec <= 12.4)
        draw_styled_button(screen, s_draw, rep_x + 16, by, half_w, bh, BTN_TEAL, "⚡", "Scanner Hub", is_scanner_pressed)
        
        # Tap on Admin Suite: 16.5s to 17.0s
        is_admin_pressed = (16.5 <= sec <= 17.0)
        draw_styled_button(screen, s_draw, rep_x + 22 + half_w, by, half_w, bh, BTN_RED, "👑", "Admin Suite", is_admin_pressed)

        by += bh + 8
        draw_styled_button(screen, s_draw, rep_x + 16, by, half_w, bh, BTN_TEAL, "📁", "Panels & Data")
        draw_styled_button(screen, s_draw, rep_x + 22 + half_w, by, half_w, bh, BTN_GREEN, "📥", "Export Hub")

        by += bh + 8
        draw_styled_button(screen, s_draw, rep_x + 16, by, full_w, bh, BTN_TEAL, "💬", "Support (@OwAtom)", False, True)

        by += bh + 8
        draw_styled_button(screen, s_draw, rep_x + 16, by, full_w, bh, BTN_RED, "🔙", "Back to Main Menu")

        # SCENE 3: Live Database Probe Toast Card (12.4s to 16.5s)
        if 12.4 <= sec < 16.5:
            pop_w = 420
            pop_h = 160
            pop_x = (screen_w - pop_w) // 2
            
            # Slide in animation
            t_slide = min(1.0, (sec - 12.4) / 0.35)
            pop_y = int((rep_y + 40) * ease_out_cubic(t_slide))

            # Translucent dark frosted modal
            s_draw.rounded_rectangle([pop_x, pop_y, pop_x + pop_w, pop_y + pop_h], radius=16, fill=(18, 30, 44), outline=(50, 180, 110), width=2)
            
            em_probe = get_emoji("🔍", 20)
            screen.paste(em_probe, (pop_x + 16, pop_y + 14), em_probe)
            s_draw.text((pop_x + 44, pop_y + 14), "LIVE DATABASE PROBE", fill=ACCENT_GREEN, font=FONT_CHAT_BOLD)
            s_draw.line([(pop_x + 14, pop_y + 42), (pop_x + pop_w - 14, pop_y + 42)], fill=(40, 65, 88))

            em_ok = get_emoji("🟢", 16)
            screen.paste(em_ok, (pop_x + 16, pop_y + 50), em_ok)
            s_draw.text((pop_x + 40, pop_y + 50), "Status: 200 OK (Open Database)", fill=ACCENT_GREEN, font=FONT_CHAT_BOLD)

            em_bar = get_emoji("📊", 16)
            screen.paste(em_bar, (pop_x + 16, pop_y + 76), em_bar)
            s_draw.text((pop_x + 40, pop_y + 76), "Indexed Records: 48,290 nodes", fill=(220, 235, 250), font=FONT_CHAT_REG)

            em_sec = get_emoji("🛡️", 16)
            screen.paste(em_sec, (pop_x + 16, pop_y + 102), em_sec)
            s_draw.text((pop_x + 40, pop_y + 102), "Read & Write: UNRESTRICTED ACCESS", fill=(255, 120, 120), font=FONT_CHAT_BOLD)

            # Verified pill badge
            s_draw.rounded_rectangle([pop_x + 16, pop_y + 128, pop_x + pop_w - 16, pop_y + 152], radius=6, fill=(35, 95, 55))
            s_draw.text((pop_x + 110, pop_y + 132), "Live Vulnerability Confirmed", fill=(255, 255, 255), font=FONT_CHAT_SMALL)

    # SCENE 4: Transition to ADMIN CONTROL SUITE (17.0s to 23.0s)
    elif 17.0 <= sec < 23.0:
        adm_y, adm_w, adm_h = ub_y + 88, 442, 450
        adm_x = 16
        s_draw.rounded_rectangle([adm_x, adm_y, adm_x + adm_w, adm_y + adm_h], radius=18, fill=BOT_BUBBLE, outline=(36, 54, 74), width=1)

        # Header
        em_crown = get_emoji("👑", 22)
        screen.paste(em_crown, (adm_x + 16, adm_y + 14), em_crown)
        s_draw.text((adm_x + 46, adm_y + 14), "ADMIN CONTROL SUITE", fill=ACCENT_ORANGE, font=FONT_CHAT_BOLD)
        s_draw.line([(adm_x + 16, adm_y + 42), (adm_x + adm_w - 16, adm_y + 42)], fill=(40, 58, 80))

        # Admin Telemetry
        admin_fields = [
            ("👥", "Total Users: 1,850 Registered", (220, 235, 250)),
            ("📊", "Total Scans: 4,200 APKs Completed", (220, 235, 250)),
            ("⚙️", "Maintenance: ONLINE (Active)", ACCENT_GREEN),
            ("📦", "Archive Channel: -1003776813052", ACCENT_BLUE),
            ("⏱", "Engine: Render Cloud 24/7 Healer", (150, 185, 215)),
            ("🛡️", "Admins: 8327850869, 7812349806", ACCENT_ORANGE)
        ]
        fy = adm_y + 50
        for em_char, ftext, fcolor in admin_fields:
            em_icon = get_emoji(em_char, 18)
            screen.paste(em_icon, (adm_x + 16, fy + 2), em_icon)
            s_draw.text((adm_x + 44, fy), ftext, fill=fcolor, font=FONT_CHAT_REG)
            fy += 26

        # Admin Controls Buttons
        by = adm_y + 215
        bh = 44
        half_w = (adm_w - 38) // 2
        full_w = adm_w - 32

        draw_styled_button(screen, s_draw, adm_x + 16, by, half_w, bh, BTN_TEAL, "🔄", "Refresh Stats")
        draw_styled_button(screen, s_draw, adm_x + 22 + half_w, by, half_w, bh, BTN_RED, "⚙️", "Maint: PAUSE")

        by += bh + 8
        draw_styled_button(screen, s_draw, adm_x + 16, by, half_w, bh, BTN_GREEN, "👥", "Export TXT")
        draw_styled_button(screen, s_draw, adm_x + 22 + half_w, by, half_w, bh, BTN_RED, "🚫", "Banned List")

        by += bh + 8
        # Tap on Archive Hub: 20.8s to 21.4s
        is_arch_pressed = (20.8 <= sec <= 21.4)
        draw_styled_button(screen, s_draw, adm_x + 16, by, half_w, bh, BTN_TEAL, "📢", "Broadcast")
        draw_styled_button(screen, s_draw, adm_x + 22 + half_w, by, half_w, bh, BTN_GREEN, "📦", "Archive Hub", is_arch_pressed)

        by += bh + 8
        draw_styled_button(screen, s_draw, adm_x + 16, by, full_w, bh, BTN_RED, "🔙", "Back to Main Menu")

        # Instant Archival Banner Toast (20.0s to 22.8s)
        if 20.0 <= sec < 22.8:
            arch_w = 400
            arch_h = 56
            arch_x = (screen_w - arch_w) // 2
            arch_y = adm_y + 110
            s_draw.rounded_rectangle([arch_x, arch_y, arch_x + arch_w, arch_y + arch_h], radius=12, fill=(16, 32, 48), outline=(60, 190, 110), width=2)
            em_box = get_emoji("📦", 22)
            screen.paste(em_box, (arch_x + 16, arch_y + 17), em_box)
            s_draw.text((arch_x + 48, arch_y + 12), "Auto-Archived to Private Channel", fill=ACCENT_GREEN, font=FONT_CHAT_BOLD)
            s_draw.text((arch_x + 48, arch_y + 32), "-1003776813052 • Message ID #7728", fill=(170, 205, 235), font=FONT_CHAT_SMALL)

    # SCENE 5: Outro Showcase (23.0s to 28.0s)
    else:
        out_y, out_w, out_h = ub_y + 88, 442, 450
        out_x = 16
        s_draw.rounded_rectangle([out_x, out_y, out_x + out_w, out_y + out_h], radius=18, fill=BOT_BUBBLE, outline=(36, 54, 74), width=1)

        em_fire = get_emoji("🔥", 24)
        screen.paste(em_fire, (out_x + 16, out_y + 14), em_fire)
        s_draw.text((out_x + 48, out_y + 14), "FIREBASE EXTRACTOR ENGINE", fill=ACCENT_ORANGE, font=FONT_CHAT_BOLD)
        s_draw.line([(out_x + 16, out_y + 44), (out_x + out_w - 16, out_y + 44)], fill=(40, 58, 80))

        s_draw.text((out_x + 16, out_y + 54), "Send any APK to instantly extract:", fill=(220, 235, 250), font=FONT_CHAT_BOLD)
        outro_points = [
            ("🌐", "Firebase Database URLs & Endpoints", ACCENT_BLUE),
            ("🔑", "API Keys, Auth Domains & App IDs", (210, 225, 240)),
            ("📡", "Server Keys & Push Messaging Credentials", (210, 225, 240)),
            ("⚡", "Live Node Probing & Security Status", ACCENT_GREEN),
            ("🛡️", "24/7 Render Cloud Auto-Healer", ACCENT_ORANGE)
        ]
        oy = out_y + 84
        for em_char, otext, ocolor in outro_points:
            em_icon = get_emoji(em_char, 18)
            screen.paste(em_icon, (out_x + 16, oy + 2), em_icon)
            s_draw.text((out_x + 44, oy), otext, fill=ocolor, font=FONT_CHAT_REG)
            oy += 26

        by = out_y + 225
        bh = 44
        half_w = (out_w - 38) // 2
        full_w = out_w - 32

        draw_styled_button(screen, s_draw, out_x + 16, by, half_w, bh, BTN_TEAL, "⚡", "Scanner Hub")
        draw_styled_button(screen, s_draw, out_x + 22 + half_w, by, half_w, bh, BTN_RED, "👑", "Admin Suite")

        by += bh + 10
        draw_styled_button(screen, s_draw, out_x + 16, by, full_w, bh, BTN_TEAL, "💬", "Support (@OwAtom)", False, True)

        by += bh + 10
        draw_styled_button(screen, s_draw, out_x + 16, by, full_w, bh, BTN_RED, "🔙", "Back to Main Menu")

    # Bottom Android Navigation
    nav_y = screen_h - 40
    s_draw.line([(0, nav_y), (screen_w, nav_y)], fill=(20, 28, 38))
    s_draw.polygon([(110, nav_y + 20), (122, nav_y + 12), (122, nav_y + 28)], fill=(130, 145, 160))
    s_draw.rounded_rectangle([screen_w // 2 - 8, nav_y + 12, screen_w // 2 + 8, nav_y + 28], radius=3, fill=(130, 145, 160))
    s_draw.rectangle([screen_w - 124, nav_y + 13, screen_w - 121, nav_y + 27], fill=(130, 145, 160))
    s_draw.rectangle([screen_w - 117, nav_y + 13, screen_w - 114, nav_y + 27], fill=(130, 145, 160))
    s_draw.rectangle([screen_w - 110, nav_y + 13, screen_w - 107, nav_y + 27], fill=(130, 145, 160))

    # Mask screen to rounded corners
    screen_mask = Image.new("L", (screen_w, screen_h), 0)
    s_mask_draw = ImageDraw.Draw(screen_mask)
    s_mask_draw.rounded_rectangle([0, 0, screen_w, screen_h], radius=36, fill=255)
    canvas.paste(screen, (screen_x, screen_y), screen_mask)

    # Glass reflection streak across phone screen
    sheen = Image.new("RGBA", (screen_w, screen_h), (0, 0, 0, 0))
    s_sheen = ImageDraw.Draw(sheen)
    s_sheen.polygon([(0, 0), (screen_w // 2, 0), (0, screen_h // 2)], fill=(255, 255, 255, 14))
    canvas.paste(sheen, (screen_x, screen_y), sheen)

    # 4. Touch Pointer Disc Physics (Modeled after reference IMG_8368.mov and video.mp4)
    # Move 1: 10.8s -> 11.8s: Glides from bottom to "⚡ Scanner Hub", taps at 11.8s - 12.4s
    # Move 2: 15.6s -> 16.5s: Glides from Scanner Hub to "👑 Admin Suite", taps at 16.5s - 17.0s
    # Move 3: 19.8s -> 20.8s: Glides to "📦 Archive Hub", taps at 20.8s - 21.4s
    if 10.8 <= sec <= 22.0:
        if sec < 13.5:
            p = min(1.0, max(0.0, (sec - 10.8) / 0.9))
            ep = ease_in_out(p)
            tx = (screen_x + 380) * (1 - ep) + (screen_x + 120) * ep
            ty = (screen_y + 700) * (1 - ep) + (screen_y + 430) * ep
            is_tap = (11.8 <= sec <= 12.4)
            ripple_color = (75, 215, 130)
        elif sec < 18.0:
            p = min(1.0, max(0.0, (sec - 15.6) / 0.8))
            ep = ease_in_out(p)
            tx = (screen_x + 120) * (1 - ep) + (screen_x + 340) * ep
            ty = (screen_y + 430) * (1 - ep) + (screen_y + 430) * ep
            is_tap = (16.5 <= sec <= 17.0)
            ripple_color = (255, 150, 45)
        else:
            p = min(1.0, max(0.0, (sec - 19.8) / 0.9))
            ep = ease_in_out(p)
            tx = (screen_x + 340) * (1 - ep) + (screen_x + 340) * ep
            ty = (screen_y + 430) * (1 - ep) + (screen_y + 535) * ep
            is_tap = (20.8 <= sec <= 21.4)
            ripple_color = (75, 215, 130)

        rad = 19 if is_tap else 24
        # Drop shadow
        draw.ellipse([(tx - rad + 2, ty - rad + 4), (tx + rad + 2, ty + rad + 4)], fill=(0, 0, 0, 50))
        # Translucent white disc
        draw.ellipse([(tx - rad, ty - rad), (tx + rad, ty + rad)], fill=(255, 255, 255, 190), outline=(255, 255, 255, 240), width=1)

        # Expanding ripple on tap
        if is_tap:
            r_scale = min(1.0, ((sec * 2.8) % 1.0))
            rip_rad = rad + int(r_scale * 32)
            rip_alpha = int((1.0 - r_scale) * 170)
            draw.ellipse([(tx - rip_rad, ty - rip_rad), (tx + rip_rad, ty + rip_rad)],
                         outline=(ripple_color[0], ripple_color[1], ripple_color[2], rip_alpha), width=2)

    out_path = os.path.join(FRAMES_DIR, f"frame_{frame_idx:04d}.png")
    canvas.save(out_path, format="PNG")
    return frame_idx

def main():
    print(f"Creating frames directory: {FRAMES_DIR}")
    os.makedirs(FRAMES_DIR, exist_ok=True)

    print(f"Rendering {TOTAL_FRAMES} 60 FPS Full HD (1920x1080) frames across 12 CPU cores...")
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 12) as executor:
        futures = [executor.submit(render_frame_worker, i) for i in range(TOTAL_FRAMES)]
        for f in futures:
            f.result()

    print(f"All {TOTAL_FRAMES} frames rendered successfully!")

    if not os.path.exists(AUDIO_FILE):
        print("Extracting 28s soundtrack from video.mp4 with smooth fadeout...")
        subprocess.run([
            "ffmpeg", "-y", "-ss", "0", "-t", str(DURATION), "-i", "/home/piyush/video.mp4",
            "-af", "afade=t=out:st=26.5:d=1.5",
            "-c:a", "aac", "-b:a", "192k", AUDIO_FILE
        ], check=True)

    print(f"Compiling 1080p 60 FPS video to {OUTPUT_VIDEO}...")
    cmd = [
        "ffmpeg", "-y",
        "-r", str(FPS),
        "-i", os.path.join(FRAMES_DIR, "frame_%04d.png"),
        "-i", AUDIO_FILE,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "16",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        OUTPUT_VIDEO
    ]
    subprocess.run(cmd, check=True)
    print(f"Successfully generated Full HD showcase video at: {OUTPUT_VIDEO}")

    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    print("Temporary frames cleaned up.")

if __name__ == "__main__":
    main()
