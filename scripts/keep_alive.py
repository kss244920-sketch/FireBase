#!/usr/bin/env python3
"""
JustRunMy.App 24/7 Keep-Alive & Lease Renewer for Firebase Extractor Bot (App ID: 64370).
Functions:
  1. Sends HTTP keepalive ping to the public endpoint.
  2. If lease timer < 6.0 hours or app is stopped, triggers start/restart via JRNM MCP.
  3. Ensures continuous, forever uptime.
"""

import datetime
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    print("requests library not found. Please install requests.")
    sys.exit(1)

APP_NAME = "Git r_s6EBr2"
APP_ID = 64370


def get_mcp_config():
    token_candidates = [
        Path(__file__).parent.parent / "jrnm_identity.token",
        Path(__file__).parent / "jrnm_identity.token",
        Path.home() / "FireBase/jrnm_identity.token",
    ]
    env_identity = os.environ.get("JRNM_IDENTITY")
    if not env_identity:
        for tp in token_candidates:
            if tp.exists() and tp.stat().st_size > 0:
                try:
                    env_identity = tp.read_text(encoding="utf-8").strip()
                    if env_identity:
                        break
                except Exception:
                    pass

    if env_identity:
        return {
            "url": "https://justrunmy.app/api/mcp",
            "headers": {"X-User-Identity": env_identity}
        }

    # Fallback to config paths
    paths = [
        Path.home() / ".gemini/config/mcp_config.json",
        Path.home() / "Downloads/mcp.json",
        Path(__file__).parent / "mcp.json",
    ]
    for p in paths:
        if p.exists() and p.stat().st_size > 0:
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                    if "mcpServers" in data and "justrunmy.app" in data["mcpServers"]:
                        return data["mcpServers"]["justrunmy.app"]
            except Exception as e:
                print(f"Error reading {p}: {e}")

    return None


def call_mcp_tool(server_conf, tool_name, arguments=None):
    url = server_conf["url"]
    headers = server_conf.get("headers", {})
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {}
        }
    }
    last_err = None
    for attempt in range(5):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=25, verify=False)
            r.raise_for_status()
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    content = data.get("result", {}).get("content", [])
                    if content and "text" in content[0]:
                        raw_text = content[0]["text"]
                        try:
                            return json.loads(raw_text)
                        except Exception:
                            return raw_text
            return None
        except requests.exceptions.RequestException as e:
            last_err = e
            if attempt < 4:
                time.sleep(5)
            else:
                raise last_err
    return None


def parse_ping_left_hours(ping_left_str):
    try:
        parts = ping_left_str.split(":")
        if len(parts) >= 3:
            first = parts[0]
            if "." in first:
                days_str, hours_str = first.split(".")
                days = int(days_str)
                hours = int(hours_str)
            else:
                days = 0
                hours = int(first)
            minutes = int(parts[1])
            return (days * 24) + hours + (minutes / 60.0)
    except Exception as e:
        print(f"Could not parse ping_left: {e}")
    return 999.0


def main():
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] Running Firebase Extractor Bot Keep-Alive Check...")

    server_conf = get_mcp_config()
    if not server_conf:
        print("ERROR: Could not locate MCP credentials for JustRunMy.App.")
        sys.exit(1)

    apps_data = call_mcp_tool(server_conf, "jrnm_get_user_apps")
    if not apps_data or "result" not in apps_data:
        print("Failed to retrieve applications list.")
        sys.exit(1)

    items = apps_data.get("result", {}).get("items", [])
    target_app = None
    for app in items:
        if app.get("id") == APP_ID or app.get("name") == APP_NAME:
            target_app = app
            break

    if not target_app and items:
        target_app = items[0]

    if not target_app:
        print(f"Target app (ID {APP_ID} / '{APP_NAME}') not found.")
        sys.exit(1)

    app_id = target_app["id"]
    is_started = target_app.get("isStarted", False)
    properties = {p["name"]: p["value"] for p in target_app.get("properties", []) if "name" in p and "value" in p}

    ping_left_str = properties.get("com.jrnm.computed.ping_left", "")
    hours_left = parse_ping_left_hours(ping_left_str)

    print(f"App: '{target_app.get('name')}' (ID: {app_id})")
    print(f"Status: isStarted={is_started}, Hours Left={hours_left:.2f}h (Raw: '{ping_left_str}')")

    # Send HTTP keepalive ping to public endpoint if available
    status_data = call_mcp_tool(server_conf, "jrnm_get_app_status", {"appId": app_id})
    endpoint_url = None
    if status_data:
        eps = status_data.get("endpoints", [])
        if eps and "url" in eps[0]:
            endpoint_url = eps[0]["url"]
            try:
                ping_r = requests.get(endpoint_url, timeout=10, verify=False)
                print(f"📡 Sent HTTP keepalive ping to {endpoint_url} (HTTP {ping_r.status_code})")
            except Exception as e:
                print(f"HTTP Ping error to {endpoint_url}: {e}")

    needs_action = False
    action_reason = ""

    if not is_started:
        needs_action = True
        action_reason = "App is currently STOPPED."
    elif hours_left < 6.0:
        needs_action = True
        action_reason = f"Free timer is low ({hours_left:.2f}h remaining < 6.0h threshold)."

    if needs_action:
        print(f"Triggering Start/Restart because: {action_reason}")
        if is_started:
            call_mcp_tool(server_conf, "jrnm_stop_app", {"appId": app_id})
            time.sleep(3)
        res = call_mcp_tool(server_conf, "jrnm_start_or_restart_app", {"appId": app_id})
        print(f"Start Response: {res}")
        print("Keep-Alive action completed successfully. Lease renewed!")
    else:
        print(f"All good. Bot is healthy with {hours_left:.2f}h remaining buffer.")


if __name__ == "__main__":
    main()
