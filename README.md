# AnneBella Firebase Extractor Bot

A Telegram bot that extracts Firebase configuration and API credentials from Android APK files.

## Features

- Extract Firebase Database URL, Project ID, Auth Domain
- Extract Google API Key & Mobile App ID
- Extract GCM Sender ID & Storage Bucket
- Detect APK packers and obfuscation
- Scan history per user
- Bot statistics tracking
- Admin logs channel
- Premium emoji formatting

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the bot:
```bash
python bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show help message |
| `/history` | View your scan history |
| `/stats` | Bot statistics |
| `/myid` | Get your Telegram ID |

## How to Use

Simply send any `.apk` file to the bot and it will automatically extract all Firebase and API credentials.

## Brand

**Annebella Firebase** — Developed by @AnneBella
