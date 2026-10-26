#!/usr/bin/env python3
"""
Firebase Bot Showcase & Promotional Video Generator
Generates a high-fidelity 720x720 30fps MP4 motion graphics video matching
Telegram's official feature presentation aesthetics, complete with native colored buttons,
device mockups, and synchronized background soundtrack.
"""

import os
import sys
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 720, 720
FPS = 30
DURATION = 13.096  # Exact duration of reference audio
TOTAL_FRAMES = int(DURATION * FPS)  # 393 frames

FRAMES_DIR = "/tmp/promo_frames"
AUDIO_FILE = "/tmp/reference_audio.aac"
OUTPUT_VIDEO = "/home/piyush/Desktop/Firebase_Bot_Showcase.mp4"

# Load Fonts
FONT_TITLE = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 32)
FONT_SIDE = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 36)
FONT_SIDE_SUB = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 17)
FONT_CHAT = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 12)
FONT_CHAT_BOLD = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 12)
FONT_BTN = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 11)
FONT_EMOJI_BASE = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)

# Pre-render Emojis
EMOJI_CACHE = {}

def get_emoji(char, size=18):
    key = (char, size)
    if key in EMOJI_CACHE:
        return EMOJI_CACHE[key]
    canvas = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.text((10, 10), char, font=FONT_EMOJI_BASE, embedded_color=True)
    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)
    canvas = canvas.resize((size, size), Image.Resampling.LANCZOS)
    EMOJI_CACHE[key] = canvas
    return canvas

def paste_emoji_text(target_img, draw, x, y, emoji_char, text, font, fill, emoji_size=16):
    if emoji_char:
        em = get_emoji(emoji_char, emoji_size)
        target_img.paste(em, (x, y + (font.size - emoji_size)//2), em)
        draw.text((x + emoji_size + 4, y), text, fill=fill, font=font)
    else:
        draw.text((x, y), text, fill=fill, font=font)

def ease_out_cubic(x):
    return 1 - pow(1 - x, 3)

def ease_in_out(x):
    return -(math.cos(math.pi * x) - 1) / 2

def render_frame_worker(frame_idx):
    sec = frame_idx / float(FPS)
    t = frame_idx / float(TOTAL_FRAMES)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # 1. Background Gradient (Telegram Blue to Vibrant Violet)
    for y in range(H):
        r_ratio = y / float(H)
        r = int(90 * (1 - r_ratio) + 122 * r_ratio)
        g = int(155 * (1 - r_ratio) + 148 * r_ratio)
        b = int(252 * (1 - r_ratio) + 255 * r_ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Floating Ambient Glow Orbs
    pulse = math.sin(sec * 1.5) * 20
    for ox, oy, orad, oalpha in [(90, 140, int(160 + pulse), 22), (610, 560, int(220 - pulse), 26)]:
        orb = Image.new("RGBA", (orad * 2, orad * 2), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(orb)
        odraw.ellipse([0, 0, orad * 2, orad * 2], fill=(255, 255, 255, oalpha))
        orb = orb.filter(ImageFilter.GaussianBlur(35))
        img.paste(orb, (ox - orad, oy - orad), orb)

    # 2. Top Header Bar: Telegram Paperplane + "Firebase Extractor"
    header_y = 34
    draw.ellipse([(55, header_y), (100, header_y + 45)], fill=(255, 255, 255))
    draw.polygon([(67, header_y + 23), (90, header_y + 14), (83, header_y + 35)], fill=(80, 150, 245))
    draw.polygon([(73, header_y + 25), (83, header_y + 35), (78, header_y + 28)], fill=(50, 120, 215))

    draw.text((112, header_y + 4), "Firebase Extractor", fill=(255, 255, 255), font=FONT_TITLE)

    # 3. Phone Animation & Geometry
    phone_w = 340
    phone_h = 574
    phone_y = 108

    # Phone slides from center (180) to left (62) during first 1.2s
    if sec < 1.2:
        slide_prog = ease_out_cubic(sec / 1.2)
        phone_x = int(180 - (180 - 62) * slide_prog)
    else:
        phone_x = 62

    # Phone Drop Shadow
    shadow = Image.new("RGBA", (phone_w + 50, phone_h + 50), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle([25, 25, phone_w + 25, phone_h + 25], radius=38, fill=(0, 0, 0, 85))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    img.paste(shadow, (phone_x - 25, phone_y - 12), shadow)

    # Phone Outer Bezel (Sleek Titanium Dark)
    draw.rounded_rectangle([phone_x, phone_y, phone_x + phone_w, phone_y + phone_h],
                           radius=36, fill=(18, 22, 28), outline=(65, 75, 88), width=3)

    # Phone Screen
    screen_x = phone_x + 8
    screen_y = phone_y + 8
    screen_w = phone_w - 16
    screen_h = phone_h - 16

    screen = Image.new("RGBA", (screen_w, screen_h), (236, 241, 246))
    s_draw = ImageDraw.Draw(screen)

    # Screen Status Bar
    s_draw.rectangle([0, 0, screen_w, 24], fill=(36, 129, 204))
    s_draw.text((16, 5), "9:41", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.rectangle([screen_w - 32, 8, screen_w - 14, 18], fill=(255, 255, 255))
    s_draw.ellipse([(screen_w // 2 - 6, 6), (screen_w // 2 + 6, 18)], fill=(12, 14, 18))

    # Telegram Header Bar inside Phone
    bar_y = 24
    bar_h = 44
    s_draw.rectangle([0, bar_y, screen_w, bar_y + bar_h], fill=(36, 129, 204))
    s_draw.polygon([(18, bar_y + 22), (26, bar_y + 14), (26, bar_y + 30)], fill=(255, 255, 255))

    # Avatar with Fire emoji
    s_draw.ellipse([(38, bar_y + 7), (68, bar_y + 37)], fill=(255, 140, 0))
    em_flame = get_emoji("🔥", 18)
    screen.paste(em_flame, (44, bar_y + 13), em_flame)

    s_draw.text((78, bar_y + 8), "Firebase Extractor", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((78, bar_y + 24), "bot • @Kkftinbot", fill=(200, 230, 255), font=FONT_CHAT)

    # CHAT MESSAGES LOGIC
    # User message: Uploading APK file
    ub_y = 80
    ub_w = 230
    ub_h = 56
    ub_x = screen_w - ub_w - 12
    s_draw.rounded_rectangle([ub_x, ub_y, ub_x + ub_w, ub_y + ub_h], radius=12, fill=(236, 255, 222))
    s_draw.ellipse([(ub_x + 8, ub_y + 10), (ub_x + 44, ub_y + 46)], fill=(100, 180, 240))
    s_draw.text((ub_x + 16, ub_y + 17), "APK", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((ub_x + 52, ub_y + 12), "production_app.apk", fill=(20, 20, 20), font=FONT_CHAT_BOLD)
    s_draw.text((ub_x + 52, ub_y + 30), "24.6 MB • 12:00 PM", fill=(100, 130, 110), font=FONT_CHAT)
    if sec >= 0.8:
        # Draw crisp double checkmark
        cx = ub_x + 170
        cy = ub_y + 36
        s_draw.line([(cx, cy), (cx + 3, cy + 4), (cx + 8, cy - 3)], fill=(50, 160, 90), width=2)
        s_draw.line([(cx + 5, cy), (cx + 8, cy + 4), (cx + 13, cy - 3)], fill=(50, 160, 90), width=2)

    # Bot Message - Phase 1: Thinking / Decompiling progress
    if 1.0 <= sec < 3.2:
        pb_y = 146
        pb_w = 285
        pb_h = 50
        s_draw.rounded_rectangle([12, pb_y, 12 + pb_w, pb_y + pb_h], radius=12, fill=(255, 255, 255))
        paste_emoji_text(screen, s_draw, 22, pb_y + 10, "⚡", "Scanning APK in parallel...", FONT_CHAT_BOLD, (40, 40, 40), 16)
        # Progress bar
        p_pct = min(1.0, (sec - 1.0) / 2.0)
        s_draw.rounded_rectangle([22, pb_y + 32, 22 + int((pb_w - 44) * p_pct), pb_y + 38], radius=3, fill=(36, 129, 204))

    # Bot Message - Phase 2 & 3: Full Scan Report Card (3.2s to 8.5s)
    if 3.2 <= sec < 8.5:
        bot_y = 146
        bot_w = 296
        bot_h = 246
        bot_x = 12
        s_draw.rounded_rectangle([bot_x, bot_y, bot_x + bot_w, bot_y + bot_h], radius=14, fill=(255, 255, 255))

        paste_emoji_text(screen, s_draw, bot_x + 10, bot_y + 8, "🔥", "FIREBASE SCAN REPORT", FONT_CHAT_BOLD, (220, 80, 0), 16)
        s_draw.line([(bot_x + 10, bot_y + 26), (bot_x + bot_w - 10, bot_y + 26)], fill=(230, 230, 230))

        paste_emoji_text(screen, s_draw, bot_x + 10, bot_y + 31, "📦", "Pkg: com.target.secureapp", FONT_CHAT_BOLD, (40, 40, 40), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10, bot_y + 49, "🌐", "DB: app-prod.firebaseio.com", FONT_CHAT, (0, 102, 204), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10, bot_y + 67, "🔑", "Key: AIzaSyBg98X_01qR92x", FONT_CHAT, (60, 60, 60), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10, bot_y + 85, "📡", "FCM: AAAA9xK201_9QzL0", FONT_CHAT, (60, 60, 60), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10, bot_y + 103, "👥", "Live Nodes: 1,420 Connected", FONT_CHAT_BOLD, (0, 145, 75), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10, bot_y + 121, "⏱", "Scan Duration: 1.42s (Lightning)", FONT_CHAT, (120, 120, 120), 14)

        # NATIVE COLORED BUTTONS
        btn_y = bot_y + 144
        btn_h = 28

        # Row 1: Check Database Live (SUCCESS GREEN)
        is_pressed = (6.0 <= sec <= 8.5)
        live_btn_color = (36, 150, 80) if is_pressed else (46, 175, 96)
        s_draw.rounded_rectangle([bot_x + 10, btn_y, bot_x + bot_w - 10, btn_y + btn_h], radius=6, fill=live_btn_color)
        paste_emoji_text(screen, s_draw, bot_x + 58, btn_y + 6, "🔍", "Check Database Live", FONT_BTN, (255, 255, 255), 14)

        # Row 2: My Scans (PRIMARY BLUE) & Statistics (SUCCESS GREEN)
        btn_y2 = btn_y + 32
        mid_w = (bot_w - 26) // 2
        s_draw.rounded_rectangle([bot_x + 10, btn_y2, bot_x + 10 + mid_w, btn_y2 + btn_h], radius=6, fill=(44, 140, 220))
        paste_emoji_text(screen, s_draw, bot_x + 28, btn_y2 + 6, "📂", "My Scans", FONT_BTN, (255, 255, 255), 14)

        s_draw.rounded_rectangle([bot_x + 16 + mid_w, btn_y2, bot_x + bot_w - 10, btn_y2 + btn_h], radius=6, fill=(46, 175, 96))
        paste_emoji_text(screen, s_draw, bot_x + 24 + mid_w, btn_y2 + 6, "📊", "Statistics", FONT_BTN, (255, 255, 255), 14)

        # Row 3: Admin Suite (DANGER RED)
        btn_y3 = btn_y2 + 32
        s_draw.rounded_rectangle([bot_x + 10, btn_y3, bot_x + bot_w - 10, btn_y3 + btn_h], radius=6, fill=(225, 60, 60))
        paste_emoji_text(screen, s_draw, bot_x + 40, btn_y3 + 6, "👑", "ADMIN CONTROL SUITE", FONT_BTN, (255, 255, 255), 14)

        # Interactive Live Modal Alert during 6.2s - 8.5s
        if 6.2 <= sec < 8.5:
            pop_y = bot_y + 20
            pop_w = 270
            pop_h = 160
            pop_x = (screen_w - pop_w) // 2
            s_draw.rounded_rectangle([pop_x, pop_y, pop_x + pop_w, pop_y + pop_h], radius=12, fill=(245, 255, 245), outline=(46, 175, 96), width=2)
            paste_emoji_text(screen, s_draw, pop_x + 12, pop_y + 12, "🔍", "LIVE DATABASE PROBE", FONT_CHAT_BOLD, (30, 130, 60), 16)
            s_draw.line([(pop_x + 10, pop_y + 36), (pop_x + pop_w - 10, pop_y + 36)], fill=(200, 230, 200))
            paste_emoji_text(screen, s_draw, pop_x + 12, pop_y + 44, "🟢", "Status: OPEN & VULNERABLE", FONT_CHAT_BOLD, (0, 140, 60), 14)
            paste_emoji_text(screen, s_draw, pop_x + 12, pop_y + 66, "📊", "Total Records: 48,290 nodes", FONT_CHAT, (50, 50, 50), 14)
            paste_emoji_text(screen, s_draw, pop_x + 12, pop_y + 86, "👥", "Live Devices: 1,420 Connected", FONT_CHAT, (50, 50, 50), 14)
            paste_emoji_text(screen, s_draw, pop_x + 12, pop_y + 106, "🛡️", "Auth: Read/Write Public", FONT_CHAT_BOLD, (200, 50, 50), 14)
            s_draw.rounded_rectangle([pop_x + 60, pop_y + 128, pop_x + pop_w - 60, pop_y + 152], radius=6, fill=(46, 175, 96))
            s_draw.text((pop_x + 85, pop_y + 132), "OK (Verified)", fill=(255, 255, 255), font=FONT_BTN)

    # Bot Message - Phase 4: Admin Control Suite (8.5s to 11.2s)
    elif 8.5 <= sec < 11.2:
        adm_y = 146
        adm_w = 296
        adm_h = 246
        adm_x = 12
        s_draw.rounded_rectangle([adm_x, adm_y, adm_x + adm_w, adm_y + adm_h], radius=14, fill=(255, 255, 255))
        paste_emoji_text(screen, s_draw, adm_x + 10, adm_y + 8, "🛡️", "ADMIN CONTROL SUITE", FONT_CHAT_BOLD, (40, 40, 40), 16)
        s_draw.line([(adm_x + 10, adm_y + 26), (adm_x + adm_w - 10, adm_y + 26)], fill=(230, 230, 230))

        paste_emoji_text(screen, s_draw, adm_x + 10, adm_y + 32, "👥", "Total Users: 1,850 Registered", FONT_CHAT_BOLD, (40, 40, 40), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10, adm_y + 50, "📊", "Total Scans: 4,200 APKs", FONT_CHAT, (40, 40, 40), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10, adm_y + 68, "⚙️", "Maintenance: ACTIVE (Online)", FONT_CHAT_BOLD, (0, 145, 75), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10, adm_y + 86, "📦", "Storage: Channel -1003776813052", FONT_CHAT, (0, 102, 204), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10, adm_y + 104, "⏱", "Uptime: 24/7 Cloud Healer Live", FONT_CHAT, (100, 100, 100), 14)

        # Admin Buttons
        ab_y = adm_y + 126
        ab_h = 26
        mid_w = (adm_w - 26) // 2

        # Row 1: Refresh (Blue) | Maint (Red)
        s_draw.rounded_rectangle([adm_x + 10, ab_y, adm_x + 10 + mid_w, ab_y + ab_h], radius=6, fill=(44, 140, 220))
        paste_emoji_text(screen, s_draw, adm_x + 22, ab_y + 5, "🔄", "Refresh", FONT_BTN, (255, 255, 255), 12)

        s_draw.rounded_rectangle([adm_x + 16 + mid_w, ab_y, adm_x + adm_w - 10, ab_y + ab_h], radius=6, fill=(225, 60, 60))
        paste_emoji_text(screen, s_draw, adm_x + 16 + mid_w, ab_y + 5, "⚙️", "Maint: PAUSE", FONT_BTN, (255, 255, 255), 12)

        # Row 2: Export (Green) | Banned (Red)
        ab_y2 = ab_y + 30
        s_draw.rounded_rectangle([adm_x + 10, ab_y2, adm_x + 10 + mid_w, ab_y2 + ab_h], radius=6, fill=(46, 175, 96))
        paste_emoji_text(screen, s_draw, adm_x + 16, ab_y2 + 5, "👥", "Export TXT", FONT_BTN, (255, 255, 255), 12)

        s_draw.rounded_rectangle([adm_x + 16 + mid_w, ab_y2, adm_x + adm_w - 10, ab_y2 + ab_h], radius=6, fill=(225, 60, 60))
        paste_emoji_text(screen, s_draw, adm_x + 16 + mid_w, ab_y2 + 5, "🚫", "Banned List", FONT_BTN, (255, 255, 255), 12)

        # Row 3: Broadcast (Blue) | Archive (Green)
        ab_y3 = ab_y2 + 30
        s_draw.rounded_rectangle([adm_x + 10, ab_y3, adm_x + 10 + mid_w, ab_y3 + ab_h], radius=6, fill=(44, 140, 220))
        paste_emoji_text(screen, s_draw, adm_x + 16, ab_y3 + 5, "📢", "Broadcast", FONT_BTN, (255, 255, 255), 12)

        s_draw.rounded_rectangle([adm_x + 16 + mid_w, ab_y3, adm_x + adm_w - 10, ab_y3 + ab_h], radius=6, fill=(46, 175, 96))
        paste_emoji_text(screen, s_draw, adm_x + 14 + mid_w, ab_y3 + 5, "📦", "Archive Hub", FONT_BTN, (255, 255, 255), 12)

    # Bot Message - Phase 5: Main Menu & Call To Action (11.2s to 13.09s)
    elif sec >= 11.2:
        wel_y = 146
        wel_w = 296
        wel_h = 246
        wel_x = 12
        s_draw.rounded_rectangle([wel_x, wel_y, wel_x + wel_w, wel_y + wel_h], radius=14, fill=(255, 255, 255))
        paste_emoji_text(screen, s_draw, wel_x + 10, wel_y + 8, "🔥", "FIREBASE EXTRACTOR ENGINE", FONT_CHAT_BOLD, (220, 80, 0), 16)
        s_draw.line([(wel_x + 10, wel_y + 26), (wel_x + wel_w - 10, wel_y + 26)], fill=(230, 230, 230))

        s_draw.text((wel_x + 10, wel_y + 32), "Send any APK to instantly extract:", fill=(40, 40, 40), font=FONT_CHAT)
        paste_emoji_text(screen, s_draw, wel_x + 10, wel_y + 50, "🌐", "Firebase Database URLs & Probes", FONT_CHAT, (0, 102, 204), 14)
        paste_emoji_text(screen, s_draw, wel_x + 10, wel_y + 68, "🔑", "API Keys, Tokens & Auth Domains", FONT_CHAT, (50, 50, 50), 14)
        paste_emoji_text(screen, s_draw, wel_x + 10, wel_y + 86, "👥", "Server Keys & Push Credentials", FONT_CHAT, (50, 50, 50), 14)
        paste_emoji_text(screen, s_draw, wel_x + 10, wel_y + 104, "⚡", "Live Node & Device Statistics", FONT_CHAT_BOLD, (0, 145, 75), 14)

        wb_y = wel_y + 128
        wb_h = 28
        # Admin Suite Button (Red)
        s_draw.rounded_rectangle([wel_x + 10, wb_y, wel_x + wel_w - 10, wb_y + wb_h], radius=6, fill=(225, 60, 60))
        paste_emoji_text(screen, s_draw, wel_x + 38, wb_y + 6, "👑", "ADMIN CONTROL SUITE", FONT_BTN, (255, 255, 255), 14)

        wb_y2 = wb_y + 32
        mid_w = (wel_w - 26) // 2
        s_draw.rounded_rectangle([wel_x + 10, wb_y2, wel_x + 10 + mid_w, wb_y2 + wb_h], radius=6, fill=(44, 140, 220))
        paste_emoji_text(screen, s_draw, wel_x + 28, wb_y2 + 6, "📂", "My Scans", FONT_BTN, (255, 255, 255), 14)

        s_draw.rounded_rectangle([wel_x + 16 + mid_w, wb_y2, wel_x + wel_w - 10, wb_y2 + wb_h], radius=6, fill=(46, 175, 96))
        paste_emoji_text(screen, s_draw, wel_x + 24 + mid_w, wb_y2 + 6, "📊", "Statistics", FONT_BTN, (255, 255, 255), 14)

        wb_y3 = wb_y2 + 32
        s_draw.rounded_rectangle([wel_x + 10, wb_y3, wel_x + wel_w - 10, wb_y3 + wb_h], radius=6, fill=(44, 140, 220))
        paste_emoji_text(screen, s_draw, wel_x + 48, wb_y3 + 6, "💬", "Support Community", FONT_BTN, (255, 255, 255), 14)

    # Mask screen to rounded corners
    screen_mask = Image.new("L", (screen_w, screen_h), 0)
    s_mask_draw = ImageDraw.Draw(screen_mask)
    s_mask_draw.rounded_rectangle([0, 0, screen_w, screen_h], radius=28, fill=255)
    img.paste(screen, (screen_x, screen_y), screen_mask)

    # 4. Right Side Typography Transitions
    text_x = 438
    text_y = 225

    if sec < 3.2:
        draw.text((text_x, text_y), "Instant\nAPK\nIntelligence", fill=(255, 255, 255), font=FONT_SIDE)
        draw.text((text_x, text_y + 135), "Drop any .apk file\nMulti-scan concurrently\nLightning-fast results", fill=(230, 245, 255), font=FONT_SIDE_SUB)
    elif sec < 6.2:
        draw.text((text_x, text_y), "Extract\nFirebase DB\n& API Keys", fill=(255, 255, 255), font=FONT_SIDE)
        draw.text((text_x, text_y + 135), "• Realtime DB URLs\n• FCM Push Server Keys\n• Google Maps & Secrets\n• C2 RAT Detection", fill=(230, 245, 255), font=FONT_SIDE_SUB)
    elif sec < 9.0:
        draw.text((text_x, text_y), "Native\nTelegram\nColors", fill=(255, 255, 255), font=FONT_SIDE)
        dot_y = text_y + 135
        for dot_color, dot_label in [((46, 175, 96), "Success Green"), ((44, 140, 220), "Primary Teal"), ((225, 60, 60), "Danger Red Admin")]:
            draw.ellipse([(text_x, dot_y + 3), (text_x + 12, dot_y + 15)], fill=dot_color)
            draw.text((text_x + 18, dot_y), dot_label, fill=(230, 245, 255), font=FONT_SIDE_SUB)
            dot_y += 24
        draw.text((text_x, dot_y + 4), "1-Tap Live Validation", fill=(255, 255, 255), font=FONT_SIDE_SUB)
    elif sec < 11.2:
        draw.text((text_x, text_y), "Admin Suite\n& Channel\nArchival", fill=(255, 255, 255), font=FONT_SIDE)
        draw.text((text_x, text_y + 135), "• Auto-Save APK to Channel\n• Interactive Admin Panel\n• TeleCore Anti-Flood", fill=(230, 245, 255), font=FONT_SIDE_SUB)
    else:
        draw.text((text_x, text_y), "24/7 Live\nCloud Engine\n@Kkftinbot", fill=(255, 255, 255), font=FONT_SIDE)
        draw.text((text_x, text_y + 135), "Free Forever on Render\nContinuous Keep-Alive\nTry it now on Telegram!", fill=(230, 245, 255), font=FONT_SIDE_SUB)

    # Save rendered frame
    out_path = os.path.join(FRAMES_DIR, f"frame_{frame_idx:04d}.png")
    img.save(out_path, format="PNG")
    return frame_idx

def main():
    print(f"Creating frames directory: {FRAMES_DIR}")
    os.makedirs(FRAMES_DIR, exist_ok=True)

    print(f"Rendering {TOTAL_FRAMES} frames across CPU cores...")
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 8) as executor:
        futures = [executor.submit(render_frame_worker, i) for i in range(TOTAL_FRAMES)]
        for f in futures:
            f.result()

    print(f"All {TOTAL_FRAMES} frames rendered successfully!")

    # Verify reference audio exists
    if not os.path.exists(AUDIO_FILE):
        print("Extracting audio from reference video...")
        subprocess.run([
            "ffmpeg", "-y", "-i", "/home/piyush/Downloads/1UkQ8pPpt8aDcHPGML0A+UnmtC-fjfas.mp4",
            "-vn", "-c:a", "copy", AUDIO_FILE
        ], check=True)

    print("Compiling video with FFmpeg & synchronizing audio...")
    cmd = [
        "ffmpeg", "-y",
        "-r", str(FPS),
        "-i", os.path.join(FRAMES_DIR, "frame_%04d.png"),
        "-i", AUDIO_FILE,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        OUTPUT_VIDEO
    ]
    subprocess.run(cmd, check=True)
    print(f"Successfully generated showcase video at: {OUTPUT_VIDEO}")

    # Clean up frames to free temp space
    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    print("Temporary frames cleaned up.")

if __name__ == "__main__":
    main()
