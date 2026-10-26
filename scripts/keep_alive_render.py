#!/usr/bin/env python3
"""
Render 24/7 Zero-Sleep Keep-Alive & Auto-Healer for @Kkftinbot (Firebase Extractor).
Pings the Render web service URL every 4 minutes to bypass Render's 15-minute inactivity spin-down.
If any service is down or unhealthy, automatically uses the Render REST API to restart it.
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    print("requests/urllib3 library not found. Please install requests urllib3.")
    sys.exit(1)

BASE_DIR = Path(__file__).parent.parent.resolve()
CONFIG_FILE = BASE_DIR / "render_config.json"
LOG_FILE = BASE_DIR / "keep_alive_render.log"

DEFAULT_SERVICES = [
    {
        "name": "kkftin-firebase-bot",
        "id": "srv-dbfg0p29lscs73a0t1gg",
        "url": "https://kkftin-firebase-bot.onrender.com"
    },
    {
        "name": "maxrummy-bot",
        "id": "srv-dbce3qrrjlhs73bn0feg",
        "url": "https://maxrummy-bot.onrender.com"
    },
    {
        "name": "bb-checker-bot",
        "id": "srv-db5lqaflk1mc73aeqteg",
        "url": "https://bb-checker-bot.onrender.com"
    },
    {
        "name": "telegram-cloud-pc-docker",
        "id": "srv-dbe4n88m7kps73capeog",
        "url": "https://telegram-cloud-pc-docker.onrender.com/health"
    }
]


def log(msg):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now_str}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_config():
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            log(f"Error loading {CONFIG_FILE}: {e}")

    api_key = os.environ.get("RENDER_API_KEY") or cfg.get("api_key") or "rnd_0ohrfCSk8YrPXQEFvf9AoStzHOTT"
    fallback_key = os.environ.get("RENDER_FALLBACK_API_KEY") or cfg.get("fallback_api_key") or "rnd_xzD7q1kZeNDWiCgR4Eaw7p6byb9n"
    owner_id = os.environ.get("RENDER_OWNER_ID") or cfg.get("owner_id") or "tea-d6fdiu88tnhs73co1950"
    service_id = os.environ.get("RENDER_SERVICE_ID") or cfg.get("service_id") or "srv-dbfg0p29lscs73a0t1gg"
    service_url = os.environ.get("RENDER_SERVICE_URL") or cfg.get("service_url") or "https://kkftin-firebase-bot.onrender.com"
    service_name = os.environ.get("RENDER_SERVICE_NAME") or cfg.get("service_name") or "kkftin-firebase-bot"
    services = cfg.get("services") or DEFAULT_SERVICES

    return {
        "api_key": api_key,
        "fallback_api_key": fallback_key,
        "owner_id": owner_id,
        "service_id": service_id,
        "service_url": service_url,
        "service_name": service_name,
        "services": services
    }


def restart_service(api_key, service_id, fallback_key=None):
    """Triggers restart via Render REST API with fallback key support."""
    keys_to_try = [k for k in [api_key, fallback_key] if k]
    for key in keys_to_try:
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "application/json"
        }
        url = f"https://api.render.com/v1/services/{service_id}/restart"
        try:
            r = requests.post(url, headers=headers, timeout=20)
            if r.status_code in (200, 201, 202):
                log(f"🔄 Successfully triggered restart for service {service_id}")
                return True
            else:
                log(f"Restart failed with key (...{key[-6:]}) status {r.status_code}: {r.text}")
        except Exception as e:
            log(f"Restart request exception: {e}")
    return False


def ping_service(api_key, svc, fallback_key=None):
    svc_name = svc.get("name", "Unknown")
    svc_id = svc.get("id")
    svc_url = svc.get("url")

    if not svc_url:
        log(f"⚠️ No URL configured for service '{svc_name}'")
        return False

    ping_url = svc_url.rstrip("/") if svc_url.endswith("/health") else svc_url.rstrip("/") + "/"
    log(f"📡 Sending Keep-Alive Ping to [{svc_name}]: {ping_url}")
    try:
        r = requests.get(ping_url, timeout=25, verify=False)
        if r.status_code == 200:
            log(f"  ✅ [{svc_name}] is 100% HEALTHY & ALIVE (HTTP {r.status_code})")
            return True
        else:
            log(f"  ⚠️ [{svc_name}] returned unexpected HTTP status: {r.status_code}")
    except requests.exceptions.RequestException as e:
        log(f"  ❌ [{svc_name}] Ping failed: {e}")

    # Self-healing auto-restart if ID is available
    if svc_id:
        log(f"  🛠️ Triggering auto-revival restart for [{svc_name}] (ID: {svc_id})...")
        restart_service(api_key, svc_id, fallback_key=fallback_key)
    return False


def ping_once():
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("Running Render 24/7 Keep-Alive & Health Ping Check...")
    cfg = load_config()
    api_key = cfg.get("api_key")
    fallback_key = cfg.get("fallback_api_key")
    services = cfg.get("services", [])

    results = []
    for svc in services:
        res = ping_service(api_key, svc, fallback_key=fallback_key)
        results.append((svc.get("name"), res))

    healthy_count = sum(1 for _, ok in results if ok)
    log(f"📊 Summary: {healthy_count}/{len(results)} services verified active.")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return healthy_count > 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Render 24/7 Keep-Alive & Auto-Healer")
    parser.add_argument("--loop", type=int, default=0, help="Run continuously for N minutes (default ping interval: 240s)")
    parser.add_argument("--interval", type=int, default=240, help="Interval between ping sweeps in seconds (default 240)")
    args = parser.parse_args()

    if args.loop <= 0:
        ping_once()
        return

    end_time = time.time() + (args.loop * 60)
    log(f"🚀 Starting continuous Keep-Alive loop for {args.loop} minutes (sweep interval: {args.interval}s)...")
    while time.time() < end_time:
        ping_once()
        remaining = end_time - time.time()
        if remaining <= 0:
            break
        sleep_dur = min(args.interval, remaining)
        log(f"💤 Sleeping for {int(sleep_dur)}s until next health check...")
        time.sleep(sleep_dur)
    log("🏁 Continuous loop completed.")


if __name__ == "__main__":
    main()
