#!/usr/bin/env python3
import datetime
import logging
import re
import subprocess
import time
from typing import Any, Dict, Optional

import requests

# ==============================
# Configuration
# ==============================

# Discord webhook URL (put your real webhook here)
WEBHOOK_URL = "https://discord.com/api/webhooks/your_webhook_id/your_token"

# Chocolate Doom server to monitor
SERVER_HOST = "example.doomserver.net"   # hostname or IP
SERVER_PORT = 2342                       # UDP port

# How often to run: every 15 minutes on the clock (:00, :15, :30, :45)
CHECK_INTERVAL_MINUTES = 15

# Webhook display name and address text
WEBHOOK_USERNAME = "My Doom Server | Chocolate Doom"
DISPLAY_ADDRESS = f"{SERVER_HOST}:{SERVER_PORT}"

# Regex for the data line, e.g.:
#   "   2 192.168.4.15          1/4 (doom2) (game running) MyServer"
#   "   2 192.168.4.15          0/8 MyServer"
QUERY_LINE_RE = re.compile(r"^\s*(\d+)\s+(\S+)\s+(\d+/\d+)\s+(.*)$")


# ==============================
# Helpers
# ==============================

def seconds_until_next_quarter() -> float:
    """
    Seconds until the next time minutes are 00, 15, 30, or 45.
    """
    now = datetime.datetime.now()
    minute = now.minute

    current_quarter = (minute // 15) * 15
    next_quarter = current_quarter + CHECK_INTERVAL_MINUTES

    if next_quarter >= 60:
        next_quarter -= 60
        target_hour = now.hour + 1
        target_date = now.date()
        if target_hour >= 24:
            target_hour = 0
            target_date = now.date() + datetime.timedelta(days=1)
        target = datetime.datetime(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
            hour=target_hour,
            minute=next_quarter,
            second=0,
            microsecond=0,
        )
    else:
        target = now.replace(
            minute=next_quarter,
            second=0,
            microsecond=0,
        )

    delta = (target - now).total_seconds()
    return max(delta, 0.0)


def query_chocdoom() -> Optional[Dict[str, Any]]:
    """
    Run `chocolate-doom -query SERVER_HOST -port SERVER_PORT` and parse the result.

    Returns a dict:
        {
            "pingMs": int,
            "ip": str,
            "players": int,
            "maxPlayers": int,
            "game": str or None,
            "inProgress": bool,
            "description": str,
        }
    or None if there is no usable output.
    """
    cmd = [
        "chocolate-doom",
        "-query",
        SERVER_HOST,
        "-port",
        str(SERVER_PORT),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        logging.warning("Failed to run chocolate-doom: %s", e)
        return None

    if proc.returncode != 0:
        logging.warning(
            "chocolate-doom exited with code %d; stderr: %s",
            proc.returncode,
            (proc.stderr or "").strip(),
        )
        return None

    ping_str = ip = players_str = rest = None

    for line in proc.stdout.splitlines():
        match = QUERY_LINE_RE.match(line)
        if match:
            ping_str, ip, players_str, rest = match.groups()
            break

    if ping_str is None:
        logging.info("No data line found in chocolate-doom output.")
        return None

    # Ping
    try:
        ping_ms = int(ping_str)
    except ValueError:
        ping_ms = -1

    # Players / max
    try:
        players_part, max_part = players_str.split("/", 1)
        players = int(players_part)
        max_players = int(max_part)
    except Exception:
        players = 0
        max_players = 0

    # Parse optional "(doom2)" etc at the front of rest
    game = None
    desc = rest

    if desc.startswith("("):
        closing = desc.find(")")
        if closing > 0:
            game = desc[1:closing]
            desc = desc[closing + 1 :].lstrip()

    # Check for "(game running)" marker
    in_progress = False
    game_running_tag = "(game running)"
    if game_running_tag in desc:
        in_progress = True
        desc = desc.replace(game_running_tag, "").strip()

    return {
        "pingMs": ping_ms,
        "ip": ip,
        "players": players,
        "maxPlayers": max_players,
        "game": game,
        "inProgress": in_progress,
        "description": desc.strip(),
    }


def send_webhook(info: Dict[str, Any]) -> None:
    """
    Send a Discord webhook for the given server info.
    Only call this when players > 0.
    """
    if not WEBHOOK_URL or "your_webhook_id" in WEBHOOK_URL:
        logging.error("WEBHOOK_URL is not configured.")
        return

    players = info.get("players", 0)
    max_players = info.get("maxPlayers", 0)
    game = info.get("game") or "Unknown"
    in_progress = info.get("inProgress", False)
    desc = info.get("description") or "(none)"

    status_text = "Game in progress" if in_progress else "Lobby"

    embed = {
        "title": "Chocolate Doom",
        "color": 0x00FF00,
        "fields": [
            {
                "name": "Address",
                "value": DISPLAY_ADDRESS,
                "inline": True,
            },
            {
                "name": "Game",
                "value": game,
                "inline": True,
            },
            {
                "name": "Status",
                "value": status_text,
                "inline": True,
            },
            {
                "name": "Players",
                "value": f"{players} / {max_players}",
                "inline": True,
            },
            {
                "name": "Description",
                "value": desc,
                "inline": False,
            },
        ],
    }

    payload = {
        "username": WEBHOOK_USERNAME,
        "content": "",
        "embeds": [embed],
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code >= 400:
            logging.error(
                "Webhook error %s: %s",
                resp.status_code,
                resp.text[:500],
            )
    except Exception as e:
        logging.exception("Failed to send webhook: %s", e)


def run_once() -> None:
    """
    One check: query server and send webhook if players > 0.
    """
    logging.info("Querying Chocolate Doom server...")
    info = query_chocdoom()
    if not info:
        logging.info("No info (server unreachable or no data).")
        return

    logging.info(
        "Got info: players=%d/%d, inProgress=%s",
        info.get("players", 0),
        info.get("maxPlayers", 0),
        info.get("inProgress", False),
    )

    if info.get("players", 0) > 0:
        send_webhook(info)
    else:
        logging.info("No players, not sending webhook.")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logging.info("Starting Chocolate Doom status bot.")

    # Force an immediate check on startup
    run_once()

    # Then run every quarter hour
    while True:
        sleep_seconds = seconds_until_next_quarter()
        logging.info(
            "Sleeping %.1f seconds until next quarter-hour check.",
            sleep_seconds,
        )
        time.sleep(sleep_seconds)
        run_once()


if __name__ == "__main__":
    main()
