#!/usr/bin/env python3
"""
Hyper-Realistic Telegram Motion Graphics Showcase Video Generator (60 FPS Edition)
Crafted specifically for @Kkftinbot (Firebase Extractor Bot) matching Telegram's official promotional video style:
- 720x720 60 FPS butter-smooth motion graphics
- 2x Retina super-sampling (1440x1440 downscaled to 720x720 with Lanczos)
- Authentic Telegram Dark Mode palette (#0e1621, #17212b, #182533, #2b5278)
- Exact native colored buttons sampled directly from user screenshot (Teal #2b6b84, Red #914236, Green #377531)
- Realistic touch pointer disc with cubic spline motion and tap ripples (modeled after IMG_8368.mov)
- Real-time APK upload, parallel decompile progress, Firebase report extraction, live DB probe, and Admin Suite
- Synchronized upbeat electronic soundtrack from Telegram reference video
"""

import os
import sys
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 2  # Super-sampling scale (2x)
W, H = 720 * S, 720 * S
FINAL_W, FINAL_H = 720, 720
FPS = 60
DURATION = 13.096  # Exact length of soundtrack
TOTAL_FRAMES = int(DURATION * FPS)  # 785 frames

FRAMES_DIR = "/tmp/promo_60fps_retina_frames"
AUDIO_FILE = "/tmp/reference_audio.aac"
OUTPUT_VIDEO = "/home/piyush/Desktop/Firebase_Bot_Showcase.mp4"

# Exact sampled colors from user screenshot & Telegram Dark Mode
BG_CHAT = (14, 22, 33)           # #0e1621
BAR_HEADER = (23, 33, 43)        # #17212b
USER_BUBBLE = (43, 82, 120)      # #2b5278
BOT_BUBBLE = (24, 37, 51)        # #182533
BTN_TEAL = (43, 107, 132)        # #2b6b84 (Scanner Hub, Panels, Support)
BTN_RED = (145, 66, 54)          # #914236 (Admin Suite, Back)
BTN_GREEN = (55, 117, 49)        # #377531 (Export Hub)
TEXT_WHITE = (255, 255, 255)
TEXT_MUTED = (160, 195, 230)
ACCENT_BLUE = (80, 175, 255)
ACCENT_GREEN = (75, 215, 130)
ACCENT_ORANGE = (255, 150, 45)

# Load Fonts at 2x
FONT_DISPLAY_BOLD = "/usr/share/fonts/truetype/noto/NotoSansDisplay-Bold.ttf"
FONT_DISPLAY_REG = "/usr/share/fonts/truetype/noto/NotoSansDisplay-Regular.ttf"
FONT_SANS_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_SANS_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

FONT_TITLE = ImageFont.truetype(FONT_DISPLAY_BOLD, 26 * S)
FONT_SIDE = ImageFont.truetype(FONT_DISPLAY_BOLD, 36 * S)
FONT_SIDE_SUB = ImageFont.truetype(FONT_SANS_REG, 17 * S)
FONT_CHAT = ImageFont.truetype(FONT_SANS_REG, 12 * S)
FONT_CHAT_BOLD = ImageFont.truetype(FONT_DISPLAY_BOLD, 13 * S)
FONT_CODE = ImageFont.truetype(FONT_SANS_BOLD, 11 * S)
FONT_BTN = ImageFont.truetype(FONT_SANS_BOLD, 12 * S)
FONT_EMOJI_BASE = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)

EMOJI_CACHE = {}

def get_emoji(char, size=16):
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

def paste_emoji_text(target_img, draw, x, y, emoji_char, text, font, fill, emoji_size=15):
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

def draw_styled_button(screen, s_draw, x, y, w, h, bg_color, emoji_char, text, is_pressed=False, has_arrow=False):
    # Press feedback
    draw_bg = tuple(min(255, c + 35) for c in bg_color) if is_pressed else bg_color
    border_col = tuple(min(255, c + 45) for c in bg_color)
    s_draw.rounded_rectangle([x, y, x + w, y + h], radius=7 * S, fill=draw_bg, outline=border_col, width=1 * S)

    # Calculate centered position
    e_size = 14 * S
    em = get_emoji(emoji_char, 14) if emoji_char else None
    em_w = (e_size + 6 * S) if em else 0
    t_bbox = s_draw.textbbox((0, 0), text, font=FONT_BTN)
    text_w = t_bbox[2] - t_bbox[0]
    total_w = em_w + text_w
    start_x = x + (w - total_w) // 2
    start_y = y + (h - FONT_BTN.size) // 2

    if em:
        screen.paste(em, (start_x, y + (h - e_size) // 2), em)
    s_draw.text((start_x + em_w, start_y), text, fill=(255, 255, 255), font=FONT_BTN)

    if has_arrow:
        ax = x + w - 14 * S
        ay = y + 7 * S
        s_draw.line([(ax, ay + 6 * S), (ax + 6 * S, ay)], fill=(200, 225, 245), width=2 * S)
        s_draw.line([(ax + 2 * S, ay), (ax + 6 * S, ay), (ax + 6 * S, ay + 4 * S)], fill=(200, 225, 245), width=2 * S)

def render_frame_worker(frame_idx):
    sec = frame_idx / float(FPS)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # 1. Background Gradient (Telegram Sky Blue to Deep Indigo Gradient)
    for y in range(H):
        r_ratio = y / float(H)
        r = int(60 * (1 - r_ratio) + 98 * r_ratio)
        g = int(130 * (1 - r_ratio) + 110 * r_ratio)
        b = int(250 * (1 - r_ratio) + 254 * r_ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Ambient Glowing Orbs
    pulse = math.sin(sec * 1.6) * 18 * S
    for ox, oy, orad, oalpha in [(120 * S, 120 * S, int(190 * S + pulse), 35),
                                (620 * S, 580 * S, int(250 * S - pulse), 40)]:
        orb = Image.new("RGBA", (orad * 2, orad * 2), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(orb)
        odraw.ellipse([0, 0, orad * 2, orad * 2], fill=(255, 255, 255, oalpha))
        orb = orb.filter(ImageFilter.GaussianBlur(38 * S))
        img.paste(orb, (ox - orad, oy - orad), orb)

    # 2. Top Header Pill
    head_w, head_h = 330 * S, 48 * S
    head_x, head_y = 44 * S, 32 * S
    pill = Image.new("RGBA", (head_w, head_h), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(pill)
    pdraw.rounded_rectangle([0, 0, head_w, head_h], radius=24 * S, fill=(255, 255, 255, 42), outline=(255, 255, 255, 90), width=1 * S)
    img.paste(pill, (head_x, head_y), pill)

    # Circular Telegram paperplane icon inside pill
    icon_size = 36 * S
    draw.ellipse([(head_x + 8 * S, head_y + 6 * S), (head_x + 8 * S + icon_size, head_y + 6 * S + icon_size)], fill=(255, 255, 255))
    ix, iy = head_x + 8 * S, head_y + 6 * S
    draw.polygon([(ix + 10 * S, iy + 18 * S), (ix + 28 * S, iy + 11 * S), (ix + 22 * S, iy + 28 * S)], fill=(45, 135, 235))
    draw.polygon([(ix + 15 * S, iy + 20 * S), (ix + 22 * S, iy + 28 * S), (ix + 18 * S, iy + 22 * S)], fill=(25, 105, 205))
    draw.text((head_x + 52 * S, head_y + 8 * S), "Firebase Extractor", fill=(255, 255, 255), font=FONT_TITLE)

    # 3. Smartphone Mockup
    phone_w = 348 * S
    phone_h = 586 * S

    # Smooth slide in from center during first 1.2s
    if sec < 1.2:
        slide_prog = ease_out_cubic(sec / 1.2)
        phone_x = int((180 * S) - ((180 - 54) * S) * slide_prog)
    elif sec > 11.2:
        # Subtle recenter float on outro
        outro_p = ease_in_out(min(1.0, (sec - 11.2) / 1.8))
        phone_x = int((54 * S) + (45 * S) * outro_p)
    else:
        phone_x = 54 * S

    # Floating levitation
    float_y = int(math.sin(sec * 1.8) * 4 * S)
    phone_y = (96 * S) + float_y

    # Drop shadow behind smartphone
    shadow = Image.new("RGBA", (phone_w + 60 * S, phone_h + 60 * S), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle([30 * S, 30 * S, phone_w + 30 * S, phone_h + 30 * S], radius=44 * S, fill=(0, 0, 0, 115))
    shadow = shadow.filter(ImageFilter.GaussianBlur(24 * S))
    img.paste(shadow, (phone_x - 30 * S, phone_y - 12 * S), shadow)

    # Outer Titanium Bezel
    draw.rounded_rectangle([phone_x, phone_y, phone_x + phone_w, phone_y + phone_h],
                           radius=42 * S, fill=(28, 34, 42), outline=(75, 88, 102), width=3 * S)

    # Screen dimensions
    screen_x = phone_x + 8 * S
    screen_y = phone_y + 8 * S
    screen_w = phone_w - 16 * S
    screen_h = phone_h - 16 * S

    screen = Image.new("RGBA", (screen_w, screen_h), BG_CHAT)
    s_draw = ImageDraw.Draw(screen)

    # Status Bar
    s_draw.text((18 * S, 6 * S), "9:41", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.rectangle([screen_w - 34 * S, 9 * S, screen_w - 14 * S, 19 * S], fill=(255, 255, 255))
    s_draw.ellipse([(screen_w // 2 - 6 * S, 7 * S), (screen_w // 2 + 6 * S, 19 * S)], fill=(8, 12, 16))

    # Telegram Chat App Bar (#17212b)
    bar_y = 26 * S
    bar_h = 44 * S
    s_draw.rectangle([0, bar_y, screen_w, bar_y + bar_h], fill=BAR_HEADER)
    s_draw.polygon([(18 * S, bar_y + 22 * S), (26 * S, bar_y + 14 * S), (26 * S, bar_y + 30 * S)], fill=(120, 145, 170))

    # Avatar with Flame Emoji
    s_draw.ellipse([(38 * S, bar_y + 7 * S), (68 * S, bar_y + 37 * S)], fill=(255, 140, 0))
    em_flame = get_emoji("🔥", 18)
    screen.paste(em_flame, (44 * S, bar_y + 13 * S), em_flame)

    s_draw.text((76 * S, bar_y + 8 * S), "Firebase Extractor Bot", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((76 * S, bar_y + 24 * S), "bot • @Kkftinbot", fill=ACCENT_BLUE, font=FONT_CHAT)

    # 3-dots menu
    s_draw.ellipse([(screen_w - 24 * S, bar_y + 16 * S), (screen_w - 20 * S, bar_y + 20 * S)], fill=(150, 175, 200))
    s_draw.ellipse([(screen_w - 24 * S, bar_y + 22 * S), (screen_w - 20 * S, bar_y + 26 * S)], fill=(150, 175, 200))
    s_draw.ellipse([(screen_w - 24 * S, bar_y + 28 * S), (screen_w - 20 * S, bar_y + 32 * S)], fill=(150, 175, 200))

    # User Message: Uploaded APK Document Bubble (#2b5278)
    ub_y = 78 * S
    ub_w = 240 * S
    ub_h = 56 * S
    ub_x = screen_w - ub_w - 12 * S
    s_draw.rounded_rectangle([ub_x, ub_y, ub_x + ub_w, ub_y + ub_h], radius=12 * S, fill=USER_BUBBLE)
    s_draw.ellipse([(ub_x + 10 * S, ub_y + 10 * S), (ub_x + 46 * S, ub_y + 46 * S)], fill=(65, 140, 210))
    s_draw.text((ub_x + 16 * S, ub_y + 18 * S), "APK", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((ub_x + 54 * S, ub_y + 12 * S), "Paytm_v12.8_secure.apk", fill=(255, 255, 255), font=FONT_CHAT_BOLD)
    s_draw.text((ub_x + 54 * S, ub_y + 30 * S), "24.6 MB • 12:00 PM", fill=TEXT_MUTED, font=FONT_CHAT)

    # Double checkmarks
    if sec >= 0.8:
        cx, cy = ub_x + 184 * S, ub_y + 35 * S
        s_draw.line([(cx, cy), (cx + 3 * S, cy + 4 * S), (cx + 8 * S, cy - 3 * S)], fill=ACCENT_GREEN, width=2 * S)
        s_draw.line([(cx + 5 * S, cy), (cx + 8 * S, cy + 4 * S), (cx + 13 * S, cy - 3 * S)], fill=ACCENT_GREEN, width=2 * S)
    else:
        spin_a = (sec * 720) % 360
        s_draw.arc([ub_x + 184 * S, ub_y + 30 * S, ub_x + 196 * S, ub_y + 42 * S], start=spin_a, end=spin_a + 270, fill=TEXT_MUTED, width=2 * S)

    # STAGE 1: Real-time Scanning Progress Animation (1.0s to 3.4s)
    if 1.0 <= sec < 3.4:
        pb_y = 144 * S
        pb_w = 308 * S
        pb_h = 76 * S
        s_draw.rounded_rectangle([12 * S, pb_y, 12 * S + pb_w, pb_y + pb_h], radius=12 * S, fill=BOT_BUBBLE, outline=(35, 52, 70), width=1 * S)
        paste_emoji_text(screen, s_draw, 22 * S, pb_y + 10 * S, "⚡", "Parallel Decompiling APK...", FONT_CHAT_BOLD, (220, 230, 240), 16)

        p_pct = min(1.0, (sec - 1.0) / 2.2)
        # Background bar
        s_draw.rounded_rectangle([22 * S, pb_y + 34 * S, 22 * S + int(pb_w - 44 * S), pb_y + 42 * S], radius=4 * S, fill=(35, 50, 68))
        # Active progress bar with cyan glow
        fill_w = int((pb_w - 44 * S) * p_pct)
        if fill_w > 0:
            s_draw.rounded_rectangle([22 * S, pb_y + 34 * S, 22 * S + fill_w, pb_y + 42 * S], radius=4 * S, fill=(40, 170, 255))

        pct_text = f"{int(p_pct * 100)}% • Extracting Dex & Firebase XML..."
        s_draw.text((22 * S, pb_y + 52 * S), pct_text, fill=(160, 195, 230), font=FONT_CHAT)

    # STAGE 2: Firebase Scan Report & EXACT Native Colored Buttons (3.4s to 7.6s)
    elif 3.4 <= sec < 7.6:
        bot_y = 142 * S
        bot_w = 308 * S
        bot_h = 328 * S
        bot_x = 12 * S
        s_draw.rounded_rectangle([bot_x, bot_y, bot_x + bot_w, bot_y + bot_h], radius=14 * S, fill=BOT_BUBBLE, outline=(35, 52, 70), width=1 * S)

        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 8 * S, "🔥", "FIREBASE SCAN REPORT", FONT_CHAT_BOLD, ACCENT_ORANGE, 16)
        s_draw.line([(bot_x + 10 * S, bot_y + 27 * S), (bot_x + bot_w - 10 * S, bot_y + 27 * S)], fill=(38, 55, 75))

        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 32 * S, "📦", "Package: com.target.secureapp", FONT_CHAT_BOLD, (220, 230, 240), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 50 * S, "🌐", "DB: kkftin-prod.firebaseio.com", FONT_CHAT, ACCENT_BLUE, 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 68 * S, "🔑", "Key: AIzaSyBg98X_01qR92x", FONT_CODE, (200, 215, 230), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 86 * S, "📡", "FCM: AAAA9xK201_9QzL0", FONT_CODE, (200, 215, 230), 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 104 * S, "👥", "Live Nodes: 1,420 Connected", FONT_CHAT_BOLD, ACCENT_GREEN, 14)
        paste_emoji_text(screen, s_draw, bot_x + 10 * S, bot_y + 122 * S, "🔓", "Status: OPEN / VULNERABLE DB!", FONT_CHAT_BOLD, (255, 100, 100), 14)

        # EXACT BUTTONS FROM USER SCREENSHOT
        # Row 1: ⚡ Scanner Hub (Teal) | 👑 Admin Suite (Red)
        btn_y1 = bot_y + 146 * S
        btn_h = 32 * S
        half_w = (bot_w - 26 * S) // 2

        is_scanner_pressed = (5.3 <= sec <= 5.8)
        draw_styled_button(screen, s_draw, bot_x + 10 * S, btn_y1, half_w, btn_h, BTN_TEAL, "⚡", "Scanner Hub", is_scanner_pressed)
        draw_styled_button(screen, s_draw, bot_x + 16 * S + half_w, btn_y1, half_w, btn_h, BTN_RED, "👑", "Admin Suite")

        # Row 2: 📁 Panels & Data (Teal) | 📥 Export Hub (Green)
        btn_y2 = btn_y1 + 38 * S
        draw_styled_button(screen, s_draw, bot_x + 10 * S, btn_y2, half_w, btn_h, BTN_TEAL, "📁", "Panels & Data")
        draw_styled_button(screen, s_draw, bot_x + 16 * S + half_w, btn_y2, half_w, btn_h, BTN_GREEN, "📥", "Export Hub")

        # Row 3: 💬 Support (@OwAtom) ↗ (Teal with diagonal arrow)
        btn_y3 = btn_y2 + 38 * S
        full_w = bot_w - 20 * S
        draw_styled_button(screen, s_draw, bot_x + 10 * S, btn_y3, full_w, btn_h, BTN_TEAL, "💬", "Support (@OwAtom)", False, True)

        # Row 4: 🔙 Back to Main Menu (Red)
        btn_y4 = btn_y3 + 38 * S
        draw_styled_button(screen, s_draw, bot_x + 10 * S, btn_y4, full_w, btn_h, BTN_RED, "🔙", "Back to Main Menu")

        # Live Database Probe Slide-in Toast Card (5.8s to 7.5s)
        if 5.8 <= sec < 7.5:
            pop_w = 296 * S
            pop_h = 138 * S
            pop_x = (screen_w - pop_w) // 2
            # Slide in animation
            slide_in = min(1.0, (sec - 5.8) / 0.3)
            pop_y = int((bot_y + 36 * S) * ease_out_cubic(slide_in))

            # Translucent dark frosted modal
            s_draw.rounded_rectangle([pop_x, pop_y, pop_x + pop_w, pop_y + pop_h], radius=12 * S, fill=(16, 26, 38), outline=(60, 160, 95), width=2 * S)
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 10 * S, "🔍", "LIVE DATABASE PROBE", FONT_CHAT_BOLD, ACCENT_GREEN, 15)
            s_draw.line([(pop_x + 10 * S, pop_y + 32 * S), (pop_x + pop_w - 10 * S, pop_y + 32 * S)], fill=(35, 55, 75))
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 38 * S, "🟢", "Status: 200 OK (Open DB)", FONT_CHAT_BOLD, ACCENT_GREEN, 13)
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 58 * S, "📊", "Indexed Records: 48,290 nodes", FONT_CHAT, (210, 225, 240), 13)
            paste_emoji_text(screen, s_draw, pop_x + 12 * S, pop_y + 78 * S, "🛡️", "Read & Write Permissions: ALLOWED", FONT_CHAT_BOLD, (255, 120, 120), 13)

            # Verified Live Badge
            s_draw.rounded_rectangle([pop_x + 12 * S, pop_y + 102 * S, pop_x + pop_w - 12 * S, pop_y + 128 * S], radius=6 * S, fill=(35, 95, 55))
            s_draw.text((pop_x + 72 * S, pop_y + 106 * S), "Live Vulnerability Confirmed", fill=(255, 255, 255), font=FONT_BTN)

    # STAGE 3: Tap on Admin Suite -> Transition to ADMIN CONTROL SUITE (7.6s to 11.2s)
    elif 7.6 <= sec < 11.2:
        adm_y = 142 * S
        adm_w = 308 * S
        adm_h = 328 * S
        adm_x = 12 * S
        s_draw.rounded_rectangle([adm_x, adm_y, adm_x + adm_w, adm_y + adm_h], radius=14 * S, fill=BOT_BUBBLE, outline=(35, 52, 70), width=1 * S)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 8 * S, "👑", "ADMIN CONTROL SUITE", FONT_CHAT_BOLD, ACCENT_ORANGE, 16)
        s_draw.line([(adm_x + 10 * S, adm_y + 27 * S), (adm_x + adm_w - 10 * S, adm_y + 27 * S)], fill=(38, 55, 75))

        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 32 * S, "👥", "Total Users: 1,850 Registered", FONT_CHAT_BOLD, (220, 230, 240), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 50 * S, "📊", "Total Scans: 4,200 APKs", FONT_CHAT, (220, 230, 240), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 68 * S, "⚙️", "Maintenance: ONLINE (Active)", FONT_CHAT_BOLD, ACCENT_GREEN, 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 86 * S, "📦", "Channel: -1003776813052", FONT_CHAT, ACCENT_BLUE, 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 104 * S, "⏱", "Uptime: 24/7 Render Cloud Healer", FONT_CHAT, (140, 165, 190), 14)
        paste_emoji_text(screen, s_draw, adm_x + 10 * S, adm_y + 122 * S, "🛡️", "Admins: 8327850869, 8219398815", FONT_CHAT_BOLD, ACCENT_ORANGE, 14)

        # Admin Control Buttons
        ab_y1 = adm_y + 146 * S
        ab_h = 32 * S
        half_w = (adm_w - 26 * S) // 2

        draw_styled_button(screen, s_draw, adm_x + 10 * S, ab_y1, half_w, ab_h, BTN_TEAL, "🔄", "Refresh Stats")
        draw_styled_button(screen, s_draw, adm_x + 16 * S + half_w, ab_y1, half_w, ab_h, BTN_RED, "⚙️", "Maint: PAUSE")

        ab_y2 = ab_y1 + 38 * S
        draw_styled_button(screen, s_draw, adm_x + 10 * S, ab_y2, half_w, ab_h, BTN_GREEN, "👥", "Export TXT")
        draw_styled_button(screen, s_draw, adm_x + 16 * S + half_w, ab_y2, half_w, ab_h, BTN_RED, "🚫", "Banned List")

        ab_y3 = ab_y2 + 38 * S
        is_archive_pressed = (9.8 <= sec <= 10.3)
        draw_styled_button(screen, s_draw, adm_x + 10 * S, ab_y3, half_w, ab_h, BTN_TEAL, "📢", "Broadcast")
        draw_styled_button(screen, s_draw, adm_x + 16 * S + half_w, ab_y3, half_w, ab_h, BTN_GREEN, "📦", "Archive Hub", is_archive_pressed)

        ab_y4 = ab_y3 + 38 * S
        full_w = adm_w - 20 * S
        draw_styled_button(screen, s_draw, adm_x + 10 * S, ab_y4, full_w, ab_h, BTN_RED, "🔙", "Back to Main Menu")

        # Archive Alert Notification (10.2s to 11.2s)
        if 10.2 <= sec < 11.2:
            arch_w = 280 * S
            arch_h = 44 * S
            arch_x = (screen_w - arch_w) // 2
            arch_y = adm_y + 90 * S
            s_draw.rounded_rectangle([arch_x, arch_y, arch_x + arch_w, arch_y + arch_h], radius=10 * S, fill=(20, 32, 45), outline=(50, 140, 80), width=2 * S)
            paste_emoji_text(screen, s_draw, arch_x + 12 * S, arch_y + 12 * S, "📦", "APK Saved to -1003776813052", FONT_CHAT_BOLD, ACCENT_GREEN, 14)

    # STAGE 4: Final Showcase & CTA (11.2s to 13.09s)
    else:
        wel_y = 142 * S
        wel_w = 308 * S
        wel_h = 328 * S
        wel_x = 12 * S
        s_draw.rounded_rectangle([wel_x, wel_y, wel_x + wel_w, wel_y + wel_h], radius=14 * S, fill=BOT_BUBBLE, outline=(35, 52, 70), width=1 * S)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 8 * S, "🔥", "FIREBASE EXTRACTOR ENGINE", FONT_CHAT_BOLD, ACCENT_ORANGE, 16)
        s_draw.line([(wel_x + 10 * S, wel_y + 27 * S), (wel_x + wel_w - 10 * S, wel_y + 27 * S)], fill=(38, 55, 75))

        s_draw.text((wel_x + 10 * S, wel_y + 34 * S), "Send any APK to instantly extract:", fill=(210, 225, 240), font=FONT_CHAT)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 54 * S, "🌐", "Firebase Database URLs & Probes", FONT_CHAT, ACCENT_BLUE, 14)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 74 * S, "🔑", "API Keys, Tokens & Auth Domains", FONT_CHAT, (210, 225, 240), 14)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 94 * S, "📡", "Server Keys & Push Credentials", FONT_CHAT, (210, 225, 240), 14)
        paste_emoji_text(screen, s_draw, wel_x + 10 * S, wel_y + 114 * S, "⚡", "Live Node & Device Statistics", FONT_CHAT_BOLD, ACCENT_GREEN, 14)

        wb_y1 = wel_y + 146 * S
        wb_h = 32 * S
        half_w = (wel_w - 26 * S) // 2
        draw_styled_button(screen, s_draw, wel_x + 10 * S, wb_y1, half_w, wb_h, BTN_TEAL, "⚡", "Scanner Hub")
        draw_styled_button(screen, s_draw, wel_x + 16 * S + half_w, wb_y1, half_w, wb_h, BTN_RED, "👑", "Admin Suite")

        wb_y2 = wb_y1 + 38 * S
        draw_styled_button(screen, s_draw, wel_x + 10 * S, wb_y2, half_w, wb_h, BTN_TEAL, "📁", "Panels & Data")
        draw_styled_button(screen, s_draw, wel_x + 16 * S + half_w, wb_y2, half_w, wb_h, BTN_GREEN, "📥", "Export Hub")

        wb_y3 = wb_y2 + 38 * S
        full_w = wel_w - 20 * S
        draw_styled_button(screen, s_draw, wel_x + 10 * S, wb_y3, full_w, wb_h, BTN_TEAL, "💬", "Support (@OwAtom)", False, True)

        wb_y4 = wb_y3 + 38 * S
        draw_styled_button(screen, s_draw, wel_x + 10 * S, wb_y4, full_w, wb_h, BTN_RED, "🔙", "Back to Main Menu")

    # Mask screen to rounded corners
    screen_mask = Image.new("L", (screen_w, screen_h), 0)
    s_mask_draw = ImageDraw.Draw(screen_mask)
    s_mask_draw.rounded_rectangle([0, 0, screen_w, screen_h], radius=32 * S, fill=255)
    img.paste(screen, (screen_x, screen_y), screen_mask)

    # Specular Glass Reflection Streak
    glass = Image.new("RGBA", (screen_w, screen_h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glass)
    gdraw.polygon([(0, 0), (screen_w // 2, 0), (0, screen_h // 2)], fill=(255, 255, 255, 14))
    img.paste(glass, (screen_x, screen_y), glass)

    # EXACT TELEGRAM TOUCH POINTER DISC (Modeled after IMG_8368.mov)
    # Move 1: 4.6s -> 5.3s: Moves to "⚡ Scanner Hub", taps at 5.4s - 5.8s
    # Move 2: 6.8s -> 7.4s: Moves to "👑 Admin Suite", taps at 7.6s - 8.0s
    # Move 3: 9.2s -> 9.8s: Moves to "📦 Archive Hub", taps at 9.9s - 10.3s
    if 4.6 <= sec <= 10.6:
        if sec < 6.4:
            p = min(1.0, max(0.0, (sec - 4.6) / 0.7))
            ep = ease_in_out(p)
            tx = (screen_x + 280 * S) * (1 - ep) + (screen_x + 85 * S) * ep
            ty = (screen_y + 440 * S) * (1 - ep) + (screen_y + 304 * S) * ep
            is_tap = (5.3 <= sec <= 5.8)
            ripple_color = (75, 215, 130)
        elif sec < 8.6:
            p = min(1.0, max(0.0, (sec - 6.6) / 0.8))
            ep = ease_in_out(p)
            tx = (screen_x + 85 * S) * (1 - ep) + (screen_x + 230 * S) * ep
            ty = (screen_y + 304 * S) * (1 - ep) + (screen_y + 304 * S) * ep
            is_tap = (7.5 <= sec <= 7.9)
            ripple_color = (255, 180, 50)
        else:
            p = min(1.0, max(0.0, (sec - 9.0) / 0.8))
            ep = ease_in_out(p)
            tx = (screen_x + 230 * S) * (1 - ep) + (screen_x + 230 * S) * ep
            ty = (screen_y + 304 * S) * (1 - ep) + (screen_y + 380 * S) * ep
            is_tap = (9.8 <= sec <= 10.3)
            ripple_color = (75, 215, 130)

        rad = 18 * S if is_tap else 23 * S
        # Drop shadow
        draw.ellipse([(tx - rad + 2 * S, ty - rad + 4 * S), (tx + rad + 2 * S, ty + rad + 4 * S)], fill=(0, 0, 0, 50))
        # Translucent white touch disc
        draw.ellipse([(tx - rad, ty - rad), (tx + rad, ty + rad)], fill=(255, 255, 255, 185), outline=(255, 255, 255, 235), width=1 * S)

        # Expanding ripple on tap
        if is_tap:
            r_scale = min(1.0, ((sec * 2.8) % 1.0))
            rip_rad = rad + int(r_scale * 30 * S)
            rip_alpha = int((1.0 - r_scale) * 160)
            draw.ellipse([(tx - rip_rad, ty - rip_rad), (tx + rip_rad, ty + rip_rad)],
                         outline=(ripple_color[0], ripple_color[1], ripple_color[2], rip_alpha), width=2 * S)

    # 4. Right Side Kinetic Typography (Official Telegram Promo Signature)
    text_x = 438 * S
    text_y = 220 * S

    if sec < 3.4:
        draw.text((text_x, text_y), "Instant\nAPK\nIntelligence", fill=TEXT_WHITE, font=FONT_SIDE)
        draw.text((text_x, text_y + 144 * S), "• Drop any .apk file\n• Concurrent multi-scan\n• Lightning-fast speed", fill=(225, 240, 255), font=FONT_SIDE_SUB)
    elif sec < 6.8:
        draw.text((text_x, text_y), "Native\nTelegram\nColors", fill=TEXT_WHITE, font=FONT_SIDE)
        dot_y = text_y + 144 * S
        for dot_color, dot_label in [(BTN_GREEN, "Success Green"), (BTN_TEAL, "Primary Teal"), (BTN_RED, "Danger Red Admin")]:
            draw.ellipse([(text_x, dot_y + 3 * S), (text_x + 12 * S, dot_y + 15 * S)], fill=dot_color)
            draw.text((text_x + 18 * S, dot_y), dot_label, fill=(225, 240, 255), font=FONT_SIDE_SUB)
            dot_y += 24 * S
        draw.text((text_x, dot_y + 6 * S), "1-Tap Live Validation", fill=TEXT_WHITE, font=FONT_SIDE_SUB)
    elif sec < 10.4:
        draw.text((text_x, text_y), "Exclusive\nAdmin\nSuite", fill=TEXT_WHITE, font=FONT_SIDE)
        draw.text((text_x, text_y + 144 * S), "• Private Admin Controls\n• Channel -1003776813052\n• Anti-Flood TeleCore", fill=(225, 240, 255), font=FONT_SIDE_SUB)
    else:
        draw.text((text_x, text_y), "24/7 Live\nOn Render\n@Kkftinbot", fill=TEXT_WHITE, font=FONT_SIDE)
        draw.text((text_x, text_y + 144 * S), "Free Forever Cloud Engine\nContinuous Auto-Healer\nAvailable on Telegram!", fill=(225, 240, 255), font=FONT_SIDE_SUB)

    # Downscale from 1440x1440 to 720x720 with LANCZOS for razor-sharp Retina antialiasing
    final_img = img.resize((FINAL_W, FINAL_H), Image.Resampling.LANCZOS)
    out_path = os.path.join(FRAMES_DIR, f"frame_{frame_idx:04d}.png")
    final_img.save(out_path, format="PNG")
    return frame_idx

def main():
    print(f"Creating frames directory: {FRAMES_DIR}")
    os.makedirs(FRAMES_DIR, exist_ok=True)

    print(f"Rendering {TOTAL_FRAMES} 60 FPS Retina 2X frames across CPU cores...")
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

    print("Compiling 60 FPS video with FFmpeg & synchronizing audio...")
    cmd = [
        "ffmpeg", "-y",
        "-r", str(FPS),
        "-i", os.path.join(FRAMES_DIR, "frame_%04d.png"),
        "-i", AUDIO_FILE,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "slow",
        "-crf", "15",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        OUTPUT_VIDEO
    ]
    subprocess.run(cmd, check=True)
    print(f"Successfully generated 60 FPS showcase video at: {OUTPUT_VIDEO}")

    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    print("Temporary frames cleaned up.")

if __name__ == "__main__":
    main()
