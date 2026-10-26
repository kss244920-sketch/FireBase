#!/usr/bin/env python3
"""
Hyper-Realistic Telegram Motion Graphics Video Generator for Firebase Bot (@Kkftinbot)
2x Retina Supersampling (1440x1440 downscaled to 720x720) for crystal-clear antialiasing,
exact Telegram Dark Mode UI (#0e1621, #17212b, #182533, #2b5278), authentic button styles,
realistic 3D smartphone chassis, specular glass reflections, interactive touch cursor,
and synchronized upbeat audio soundtrack.
"""

import os
import sys
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 2  # Super-sampling factor for Retina crispness
W, H = 720 * S, 720 * S
FINAL_W, FINAL_H = 720, 720
FPS = 30
DURATION = 13.096  # Exact duration of reference audio
TOTAL_FRAMES = int(DURATION * FPS)  # 392 frames

FRAMES_DIR = "/tmp/promo_retina_frames"
AUDIO_FILE = "/tmp/reference_audio.aac"
OUTPUT_VIDEO = "/home/piyush/Desktop/Firebase_Bot_Showcase.mp4"

# Fonts scaled at 2x
FONT_TITLE = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 32 * S)
FONT_SIDE = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 36 * S)
FONT_SIDE_SUB = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 17 * S)
FONT_CHAT = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 12 * S)
FONT_CHAT_BOLD = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 12 * S)
FONT_CODE = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 11 * S)
FONT_BTN = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 11 * S)
FONT_EMOJI_BASE = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)

EMOJI_CACHE = {}

def get_emoji(char, size=18):
    size_scaled = size * S
    key = (char, size_scaled)
    if key in EMOJI_CACHE:
        return EMOJI_CACHE[key]
    canvas = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.text((10, 10), char, font=FONT_EMOJI_BASE, embedded_color=True)
    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop(bbox)
    canvas = canvas.resize((size_scaled, size_scaled), Image.Resampling.LANCZOS)
    EMOJI_CACHE[key] = canvas
    return canvas

def paste_emoji_text(target_img, draw, x, y, emoji_char, text, font, fill, emoji_size=16):
    e_size = emoji_size * S
    if emoji_char:
        em = get_emoji(emoji_char, emoji_size)
        target_img.paste(em, (x, y + (font.size - e_size) // 2), em)
        draw.text((x + e_size + 6 * S, y), text, fill=fill, font=font)
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

    # 1. Background Gradient (Vibrant Telegram Sky Blue to Deep Indigo)
    for y in range(H):
        r_ratio = y / float(H)
        r = int(52 * (1 - r_ratio) + 94 * r_ratio)
        g = int(122 * (1 - r_ratio) + 104 * r_ratio)
        b = int(246 * (1 - r_ratio) + 252 * r_ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Floating Ambient Glowing Orbs
    pulse = math.sin(sec * 1.5) * 15 * S
    for ox, oy, orad, oalpha in [(110 * S, 130 * S, int(180 * S + pulse), 32),
                                (610 * S, 570 * S, int(240 * S - pulse), 38)]:
        orb = Image.new("RGBA", (orad * 2, orad * 2), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(orb)
        odraw.ellipse([0, 0, orad * 2, orad * 2], fill=(255, 255, 255, oalpha))
        orb = orb.filter(ImageFilter.GaussianBlur(35 * S))
        img.paste(orb, (ox - orad, oy - orad), orb)

    # 2. Top Header Bar (Glassmorphic Translucent Pill)
    head_w, head_h = 326 * S, 48 * S
    head_x, head_y = 44 * S, 32 * S
    pill = Image.new("RGBA", (head_w, head_h), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(pill)
    pdraw.rounded_rectangle([0, 0, head_w, head_h], radius=24 * S, fill=(255, 255, 255, 42), outline=(255, 255, 255, 85), width=1 * S)
    img.paste(pill, (head_x, head_y), pill)

    # Telegram Circular Icon inside pill
    icon_size = 36 * S
    draw.ellipse([(head_x + 8 * S, head_y + 6 * S), (head_x + 8 * S + icon_size, head_y + 6 * S + icon_size)], fill=(255, 255, 255))
    ix, iy = head_x + 8 * S, head_y + 6 * S
    draw.polygon([(ix + 10 * S, iy + 18 * S), (ix + 28 * S, iy + 11 * S), (ix + 22 * S, iy + 28 * S)], fill=(45, 135, 235))
    draw.polygon([(ix + 15 * S, iy + 20 * S), (ix + 22 * S, iy + 28 * S), (ix + 18 * S, iy + 22 * S)], fill=(25, 105, 205))

    draw.text((head_x + 52 * S, head_y + 6 * S), "Firebase Extractor", fill=(255, 255, 255), font=FONT_TITLE)

    # 3. Smartphone Mockup (Realistic Titanium Bezel & Dark Mode Screen)
    phone_w = 346 * S
    phone_h = 582 * S

    # Smooth slide in from center (180) to left (58) during first 1.2s
    if sec < 1.2:
        slide_prog = ease_out_cubic(sec / 1.2)
        phone_x = int((180 * S) - ((180 - 58) * S) * slide_prog)
    else:
        phone_x = 58 * S

    # Floating levitation effect
    float_y = int(math.sin(sec * 1.8) * 4 * S)
    phone_y = (98 * S) + float_y

    # Drop shadow under phone
    shadow = Image.new("RGBA", (phone_w + 60 * S, phone_h + 60 * S), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle([30 * S, 30 * S, phone_w + 30 * S, phone_h + 30 * S], radius=44 * S, fill=(0, 0, 0, 115))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24 * S))
    img.paste(shadow, (phone_x - 30 * S, phone_y - 12 * S), shadow)

    # Outer Titanium Bezel
    draw.rounded_rectangle([phone_x, phone_y, phone_x + phone_w, phone_y + phone_h],
                           radius=42 * S, fill=(28, 34, 42), outline=(75, 88, 102), width=3 * S)

    # Screen inside phone
    screen_x = phone_x + 8 * S
    screen_y = phone_y + 8 * S
    screen_w = phone_w - 16 * S
    screen_h = phone_h - 16 * S

    screen = Image.new("RGBA", (screen_w, screen_h), (14, 22, 33))  # Telegram Dark Mode #0e1621
    s_draw = ImageDraw.Draw(screen)

    # Status Bar
    s_draw.text((18 * S, 6 * S), "9:41", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.rectangle([screen_w - 34 * S, 9 * S, screen_w - 14 * S, 19 * S], fill=(255, 255, 255))
    s_draw.ellipse([(screen_w // 2 - 6 * S, 7 * S), (screen_w // 2 + 6 * S, 19 * S)], fill=(8, 12, 16))

    # Telegram Chat App Bar (#17212b)
    bar_y = 26 * S
    bar_h = 44 * S
    s_draw.rectangle([0, bar_y, screen_w, bar_y + bar_h], fill=(23, 33, 43))
    s_draw.polygon([(18 * S, bar_y + 22 * S), (26 * S, bar_y + 14 * S), (26 * S, bar_y + 30 * S)], fill=(120, 145, 170))

    # Avatar with Flame Emoji
    s_draw.ellipse([(38 * S, bar_y + 7 * S), (68 * S, bar_y + 37 * S)], fill=(255, 140, 0))
    em_flame = get_emoji("🔥", 18)
    screen.paste(em_flame, (44 * S, bar_y + 13 * S), em_flame)

    s_draw.text((78 * S, bar_y + 8 * S), "Firebase Extractor Bot", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((78 * S, bar_y + 24 * S), "bot • @Kkftinbot", fill=(100, 165, 225), font=FONT_CHAT)

    # User Message: Uploaded APK Document Bubble (#2b5278)
    ub_y = 80 * S
    ub_w = 236 * S
    ub_h = 58 * S
    ub_x = screen_w - ub_w - 12 * S
    s_draw.rounded_rectangle([ub_x, ub_y, ub_x + ub_w, ub_y + ub_h], radius=12 * S, fill=(43, 82, 120))
    s_draw.ellipse([(ub_x + 10 * S, ub_y + 11 * S), (ub_x + 46 * S, ub_y + 47 * S)], fill=(65, 140, 210))
    s_draw.text((ub_x + 18 * S, ub_y + 19 * S), "APK", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((ub_x + 54 * S, ub_y + 13 * S), "production_game.apk", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((ub_x + 54 * S, ub_y + 31 * S), "24.6 MB • 12:00 PM", fill=(160, 195, 230), font=FONT_CHAT)

    # Double checkmarks
    if sec >= 0.8:
        cx, cy = ub_x + 172 * S, ub_y + 36 * S
        s_draw.line([(cx, cy), (cx + 3 * S, cy + 4 * S), (cx + 8 * S, cy - 3 * S)], fill=(75, 190, 120), width=2 * S)
        s_draw.line([(cx + 5 * S, cy), (cx + 8 * S, cy + 4 * S), (cx + 13 * S, cy - 3 * S)], fill=(75, 190, 120), width=2 * S)
    else:
        # Animated upload progress circle
        spin_a = (sec * 720) % 360
        s_draw.arc([ub_x + 172 * S, ub_y + 30 * S, ub_x + 186 * S, ub_y + 44 * S], start=spin_a, end=spin_a + 270, fill=(160, 195, 230), width=2 * S)

    # Bot Message - Stage 1 (1.0s to 3.0s): Parallel Decompiling progress
    if 1.0 <= sec < 3.0:
        pb_y = 148 * S
        pb_w = 296 * S
        pb_h = 52 * S
        s_draw.rounded_rectangle([12 * S, pb_y, 12 * S + pb_w, pb_y + pb_h], radius=12 * S, fill=(24, 37, 51), outline=(35, 52, 70), width=1 * S)
        paste_emoji_text(screen, s_draw, 22 * S, pb_y + 10 * S, "⚡", "Scanning APK in parallel...", FONT_CHAT_BOLD, (220, 230, 240), 16)
        p_pct = min(1.0, (sec - 1.0) / 1.8)
        # Background bar
        s_draw.rounded_rectangle([22 * S, pb_y + 32 * S, 22 * S + int((pb_w - 44 * S)), pb_y + 38 * S], radius=3 * S, fill=(35, 50, 68))
        # Active progress bar with cyan glow
        s_draw.rounded_rectangle([22 * S, pb_y + 32 * S, 22 * S + int((pb_w - 44 * S) * p_pct), pb_y + 38 * S], radius=3 * S, fill=(40, 160, 240))

    # Bot Message - Stage 2 & 3 (3.0s to 8.5s): Extraction Report & Native Colored Buttons
    if 3.0 <= sec < 8.5:
        bot_y = 148 * S
        bot_w = 306 * S
        bot_h = 246 * S
        bot_x = 12 * S
        s_draw.rounded_rectangle([bot_x, bot_y, bot_x + bot_w, bot_y + bot_h], radius=14 * S, fill=(24, 37, 51), outline=(35, 52, 70), width=1 * S)

        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 8 * S, "🔥", "FIREBASE SCAN REPORT", FONT_CHAT_BOLD, (255, 145, 40), 16)
        s_draw.line([(bot_x + 10 * S, bot_y + 27 * S), (bot_x + bot_w - 10 * S, bot_y + 27 * S)], fill=(38, 55, 75))

        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 33 * S, "📦", "Package: com.target.secureapp", FONT_CHAT_BOLD, (220, 230, 240), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 51 * S, "🌐", "DB: app-prod.firebaseio.com", FONT_CHAT, (80, 175, 255), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 69 * S, "🔑", "Key: AIzaSyBg98X_01qR92x", FONT_CODE, (200, 215, 230), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 87 * S, "📡", "FCM: AAAA9xK201_9QzL0", FONT_CODE, (200, 215, 230), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 105 * S, "👥", "Live Nodes: 1,420 Connected", FONT_CHAT_BOLD, (75, 210, 130), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 123 * S, "⏱", "Scan Time: 1.42s (Lightning)", FONT_CHAT, (140, 165, 190), 14)

        # EXACT NATIVE COLORED BUTTONS FROM USER SCREENSHOT
        btn_y = bot_y + 144 * S
        btn_h = 28 * S

        # Row 1: Check Database Live (Success Green: #255832)
        is_pressed = (5.8 <= sec <= 8.5)
        live_btn_col = (48, 115, 65) if is_pressed else (37, 88, 50)
        s_draw.rounded_rectangle([bot_x + 10 * S, btn_y, bot_x + bot_w - 10 * S, btn_y + btn_h], radius=6 * S, fill=live_btn_col, outline=(55, 130, 75), width=1 * S)
        paste_emoji_text(screen, s_draw, bot_x + 64 * S, btn_y + 6 * S, "🔍", "Check Database Live", FONT_BTN, (255, 255, 255), 14)

        # Row 2: My Scans (Primary Teal: #20455c) & Statistics (Success Green: #255832)
        btn_y2 = btn_y + 32 * S
        mid_w = (bot_w - 26 * S) // 2
        s_draw.rounded_rectangle([bot_x + 10 * S, btn_y2, bot_x + 10 * S + mid_w, btn_y2 + btn_h], radius=6 * S, fill=(32, 69, 92), outline=(45, 95, 125), width=1 * S)
        paste_emoji_text(screen, s_draw, bot_x + 32 * S, btn_y2 + 6 * S, "📂", "My Scans", FONT_BTN, (255, 255, 255), 14)

        s_draw.rounded_rectangle([bot_x + 16 * S + mid_w, btn_y2, bot_x + bot_w - 10 * S, btn_y2 + btn_h], radius=6 * S, fill=(37, 88, 50), outline=(50, 120, 68), width=1 * S)
        paste_emoji_text(screen, s_draw, bot_x + 28 * S + mid_w, btn_y2 + 6 * S, "📊", "Statistics", FONT_BTN, (255, 255, 255), 14)

        # Row 3: Admin Suite (Danger Red: #662a2a)
        btn_y3 = btn_y2 + 32 * S
        s_draw.rounded_rectangle([bot_x + 10 * S, btn_y3, bot_x + bot_w - 10 * S, btn_y3 + btn_h], radius=6 * S, fill=(102, 42, 42), outline=(140, 58, 58), width=1 * S)
        paste_emoji_text(screen, s_draw, bot_x + 46 * S, btn_y3 + 6 * S, "👑", "ADMIN CONTROL SUITE", FONT_BTN, (255, 255, 255), 14)

        # Interactive Finger Tap & Live Modal Alert (6.0s to 8.5s)
        if 6.0 <= sec < 8.5:
            # Live Probe Result Popup Modal
            pop_y = bot_y + 20 * S
            pop_w = 280 * S
            pop_h = 166 * S
            pop_x = (screen_w - pop_w) // 2
            # Dark Frosted Glass Modal
            s_draw.rounded_rectangle([pop_x, pop_y, pop_x + pop_w, pop_y + pop_h], radius=14 * S, fill=(18, 30, 42), outline=(50, 130, 75), width=2 * S)
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 12 * S, "🔍", "LIVE DATABASE PROBE", FONT_CHAT_BOLD, (75, 210, 130), 16)
            s_draw.line([(pop_x + 10 * S, pop_y + 36 * S), (pop_x + pop_w - 10 * S, pop_y + 36 * S)], fill=(35, 55, 75))
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 44 * S, "🟢", "Status: OPEN & VULNERABLE", FONT_CHAT_BOLD, (75, 220, 130), 14)
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 66 * S, "📊", "Total Records: 48,290 nodes", FONT_CHAT, (210, 225, 240), 14)
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 86 * S, "👥", "Live Devices: 1,420 Connected", FONT_CHAT, (210, 225, 240), 14)
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 106 * S, "🛡️", "Auth: Public Read/Write Allowed", FONT_CHAT_BOLD, (255, 110, 110), 14)
            # Dismiss button
            s_draw.rounded_rectangle([pop_x + 65 * S, pop_y + 130 * S, pop_x + pop_w - 65 * S, pop_y + 156 * S], radius=6 * S, fill=(37, 88, 50))
            s_draw.text((pop_x + 94 * S, pop_y + 134 * S), "OK (Verified)", fill=(255, 255, 255), font=FONT_BTN)

    # Bot Message - Stage 4 (8.5s to 11.2s): Admin Control Suite
    elif 8.5 <= sec < 11.2:
        adm_y = 148 * S
        adm_w = 306 * S
        adm_h = 246 * S
        adm_x = 12 * S
        s_draw.rounded_rectangle([adm_x, adm_y, adm_x + adm_w, adm_y + adm_h], radius=14 * S, fill=(24, 37, 51), outline=(35, 52, 70), width=1 * S)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 8 * S, "🛡️", "ADMIN CONTROL SUITE", FONT_CHAT_BOLD, (255, 145, 40), 16)
        s_draw.line([(adm_x + 10 * S, adm_y + 27 * S), (adm_x + adm_w - 10 * S, adm_y + 27 * S)], fill=(38, 55, 75))

        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 33 * S, "👥", "Total Users: 1,850 Registered", FONT_CHAT_BOLD, (220, 230, 240), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 51 * S, "📊", "Total Scans: 4,200 APKs", FONT_CHAT, (220, 230, 240), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 69 * S, "⚙️", "Maintenance: ACTIVE (Online)", FONT_CHAT_BOLD, (75, 210, 130), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 87 * S, "📦", "Storage: Channel -1003776813052", FONT_CHAT, (80, 175, 255), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 105 * S, "⏱", "Uptime: 24/7 Cloud Healer Live", FONT_CHAT, (140, 165, 190), 14)

        # Admin Action Buttons (Dark themed from user screenshot)
        ab_y = adm_y + 126 * S
        ab_h = 26 * S
        mid_w = (adm_w - 26 * S) // 2

        # Row 1: Refresh (Teal) | Maint (Red)
        s_draw.rounded_rectangle([adm_x + 10 * S, ab_y, adm_x + 10 * S + mid_w, ab_y + ab_h], radius=6 * S, fill=(32, 69, 92), outline=(45, 95, 125), width=1 * S)
        paste_emoji_text(screen, s_draw, adm_x + 22 * S, ab_y + 5 * S, "🔄", "Refresh", FONT_BTN, (255, 255, 255), 12)

        s_draw.rounded_rectangle([adm_x + 16 * S + mid_w, ab_y, adm_x + adm_w - 10 * S, ab_y + ab_h], radius=6 * S, fill=(102, 42, 42), outline=(140, 58, 58), width=1 * S)
        paste_emoji_text(screen, s_draw, adm_x + 16 * S + mid_w, ab_y + 5 * S, "⚙️", "Maint: PAUSE", FONT_BTN, (255, 255, 255), 12)

        # Row 2: Export (Green) | Banned (Red)
        ab_y2 = ab_y + 30 * S
        s_draw.rounded_rectangle([adm_x + 10 * S, ab_y2, adm_x + 10 * S + mid_w, ab_y2 + ab_h], radius=6 * S, fill=(37, 88, 50), outline=(50, 120, 68), width=1 * S)
        paste_emoji_text(screen, s_draw, adm_x + 16 * S, ab_y2 + 5 * S, "👥", "Export TXT", FONT_BTN, (255, 255, 255), 12)

        s_draw.rounded_rectangle([adm_x + 16 * S + mid_w, ab_y2, adm_x + adm_w - 10 * S, ab_y2 + ab_h], radius=6 * S, fill=(102, 42, 42), outline=(140, 58, 58), width=1 * S)
        paste_emoji_text(screen, s_draw, adm_x + 16 * S + mid_w, ab_y2 + 5 * S, "🚫", "Banned List", FONT_BTN, (255, 255, 255), 12)

        # Row 3: Broadcast (Teal) | Archive (Green)
        ab_y3 = ab_y2 + 30 * S
        s_draw.rounded_rectangle([adm_x + 10 * S, ab_y3, adm_x + 10 * S + mid_w, ab_y3 + ab_h], radius=6 * S, fill=(32, 69, 92), outline=(45, 95, 125), width=1 * S)
        paste_emoji_text(screen, s_draw, adm_x + 16 * S, ab_y3 + 5 * S, "📢", "Broadcast", FONT_BTN, (255, 255, 255), 12)

        s_draw.rounded_rectangle([adm_x + 16 * S + mid_w, ab_y3, adm_x + adm_w - 10 * S, ab_y3 + ab_h], radius=6 * S, fill=(37, 88, 50), outline=(50, 120, 68), width=1 * S)
        paste_emoji_text(screen, s_draw, adm_x + 14 * S + mid_w, ab_y3 + 5 * S, "📦", "Archive Hub", FONT_BTN, (255, 255, 255), 12)

    # Bot Message - Stage 5 (11.2s to 13.09s): Final Welcome & CTA
    elif sec >= 11.2:
        wel_y = 148 * S
        wel_w = 306 * S
        wel_h = 246 * S
        wel_x = 12 * S
        s_draw.rounded_rectangle([wel_x, wel_y, wel_x + wel_w, wel_y + wel_h], radius=14 * S, fill=(24, 37, 51), outline=(35, 52, 70), width=1 * S)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 8 * S, "🔥", "FIREBASE EXTRACTOR ENGINE", FONT_CHAT_BOLD, (255, 145, 40), 16)
        s_draw.line([(wel_x + 10 * S, wel_y + 27 * S), (wel_x + wel_w - 10 * S, wel_y + 27 * S)], fill=(38, 55, 75))

        s_draw.text((wel_x + 10 * S, wel_y + 33 * S), "Send any APK to instantly extract:", fill=(210, 225, 240), font=FONT_CHAT)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 51 * S, "🌐", "Firebase Database URLs & Probes", FONT_CHAT, (80, 175, 255), 14)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 69 * S, "🔑", "API Keys, Tokens & Auth Domains", FONT_CHAT, (210, 225, 240), 14)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 87 * S, "👥", "Server Keys & Push Credentials", FONT_CHAT, (210, 225, 240), 14)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 105 * S, "⚡", "Live Node & Device Statistics", FONT_CHAT_BOLD, (75, 210, 130), 14)

        wb_y = wel_y + 128 * S
        wb_h = 28 * S
        # Admin Suite Button (Red)
        s_draw.rounded_rectangle([wel_x + 10 * S, wb_y, wel_x + wel_w - 10 * S, wb_y + wb_h], radius=6 * S, fill=(102, 42, 42), outline=(140, 58, 58), width=1 * S)
        paste_emoji_text(screen, s_draw, wel_x + 44 * S, wb_y + 6 * S, "👑", "ADMIN CONTROL SUITE", FONT_BTN, (255, 255, 255), 14)

        wb_y2 = wb_y + 32 * S
        mid_w = (wel_w - 26 * S) // 2
        s_draw.rounded_rectangle([wel_x + 10 * S, wb_y2, wel_x + 10 * S + mid_w, wb_y2 + wb_h], radius=6 * S, fill=(32, 69, 92), outline=(45, 95, 125), width=1 * S)
        paste_emoji_text(screen, s_draw, wel_x + 32 * S, wb_y2 + 6 * S, "📂", "My Scans", FONT_BTN, (255, 255, 255), 14)

        s_draw.rounded_rectangle([wel_x + 16 * S + mid_w, wb_y2, wel_x + wel_w - 10 * S, wb_y2 + wb_h], radius=6 * S, fill=(37, 88, 50), outline=(50, 120, 68), width=1 * S)
        paste_emoji_text(screen, s_draw, wel_x + 28 * S + mid_w, wb_y2 + 6 * S, "📊", "Statistics", FONT_BTN, (255, 255, 255), 14)

        wb_y3 = wb_y2 + 32 * S
        s_draw.rounded_rectangle([wel_x + 10 * S, wb_y3, wel_x + wel_w - 10 * S, wb_y3 + wb_h], radius=6 * S, fill=(32, 69, 92), outline=(45, 95, 125), width=1 * S)
        paste_emoji_text(screen, s_draw, wel_x + 48 * S, wb_y3 + 6 * S, "💬", "Support Community", FONT_BTN, (255, 255, 255), 14)

    # Mask screen to rounded corners
    screen_mask = Image.new("L", (screen_w, screen_h), 0)
    s_mask_draw = ImageDraw.Draw(screen_mask)
    s_mask_draw.rounded_rectangle([0, 0, screen_w, screen_h], radius=32 * S, fill=255)
    img.paste(screen, (screen_x, screen_y), screen_mask)

    # Specular Glass Reflection Streak across screen
    glass = Image.new("RGBA", (screen_w, screen_h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glass)
    gdraw.polygon([(0, 0), (screen_w // 2, 0), (0, screen_h // 2)], fill=(255, 255, 255, 14))
    img.paste(glass, (screen_x, screen_y), glass)

    # Animated Touch Cursor during Interactive Scene (5.4s to 6.5s)
    if 5.4 <= sec <= 6.5:
        cur_prog = min(1.0, (sec - 5.4) / 0.7)
        cx = int((screen_x + 240 * S) * (1 - cur_prog) + (screen_x + 160 * S) * cur_prog)
        cy = int((screen_y + 360 * S) * (1 - cur_prog) + (screen_y + 306 * S) * cur_prog)
        draw.ellipse([(cx - 16 * S, cy - 16 * S), (cx + 16 * S, cy + 16 * S)], fill=(255, 255, 255, 120), outline=(255, 255, 255, 220), width=2 * S)
        draw.ellipse([(cx - 6 * S, cy - 6 * S), (cx + 6 * S, cy + 6 * S)], fill=(255, 255, 255, 240))

    # 4. Right Side Kinetic Typography
    text_x = 438 * S
    text_y = 225 * S

    if sec < 3.0:
        draw.text((text_x, text_y), "Instant\nAPK\nIntelligence", fill=(255, 255, 255), font=FONT_SIDE)
        draw.text((text_x, text_y + 140 * S), "Drop any .apk file\nMulti-scan concurrently\nLightning-fast results", fill=(225, 240, 255), font=FONT_SIDE_SUB)
    elif sec < 6.0:
        draw.text((text_x, text_y), "Extract\nFirebase DB\n& API Keys", fill=(255, 255, 255), font=FONT_SIDE)
        draw.text((text_x, text_y + 140 * S), "• Realtime DB URLs\n• FCM Push Server Keys\n• Google Maps & Secrets\n• C2 RAT Detection", fill=(225, 240, 255), font=FONT_SIDE_SUB)
    elif sec < 8.8:
        draw.text((text_x, text_y), "Native\nTelegram\nColors", fill=(255, 255, 255), font=FONT_SIDE)
        dot_y = text_y + 140 * S
        for dot_color, dot_label in [((46, 175, 96), "Success Green"), ((44, 140, 220), "Primary Teal"), ((225, 60, 60), "Danger Red Admin")]:
            draw.ellipse([(text_x, dot_y + 3 * S), (text_x + 12 * S, dot_y + 15 * S)], fill=dot_color)
            draw.text((text_x + 18 * S, dot_y), dot_label, fill=(225, 240, 255), font=FONT_SIDE_SUB)
            dot_y += 24 * S
        draw.text((text_x, dot_y + 6 * S), "1-Tap Live Validation", fill=(255, 255, 255), font=FONT_SIDE_SUB)
    elif sec < 11.2:
        draw.text((text_x, text_y), "Admin Suite\n& Channel\nArchival", fill=(255, 255, 255), font=FONT_SIDE)
        draw.text((text_x, text_y + 140 * S), "• Auto-Save APK to Channel\n• Interactive Admin Panel\n• TeleCore Anti-Flood", fill=(225, 240, 255), font=FONT_SIDE_SUB)
    else:
        draw.text((text_x, text_y), "24/7 Live\nCloud Engine\n@Kkftinbot", fill=(255, 255, 255), font=FONT_SIDE)
        draw.text((text_x, text_y + 140 * S), "Free Forever on Render\nContinuous Keep-Alive\nTry it now on Telegram!", fill=(225, 240, 255), font=FONT_SIDE_SUB)

    # Downscale from 1440x1440 to 720x720 with LANCZOS for razor-sharp Retina antialiasing
    final_img = img.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS)
    out_path = os.path.join(FRAMES_DIR, f"frame_{frame_idx:04d}.png")
    final_img.save(out_path, format="PNG")
    return frame_idx

def main():
    print(f"Creating frames directory: {FRAMES_DIR}")
    os.makedirs(FRAMES_DIR, exist_ok=True)

    print(f"Rendering {TOTAL_FRAMES} Retina 2X frames across CPU cores...")
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 8) as executor:
        futures = [executor.submit(render_frame_worker, i) for i in range(TOTAL_FRAMES)]
        for f in futures:
            f.result()

    print(f"All {TOTAL_FRAMES} frames rendered successfully!")

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
        "-preset", "slow",
        "-crf", "16",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        OUTPUT_VIDEO
    ]
    subprocess.run(cmd, check=True)
    print(f"Successfully generated showcase video at: {OUTPUT_VIDEO}")

    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    print("Temporary frames cleaned up.")

if __name__ == "__main__":
    main()
