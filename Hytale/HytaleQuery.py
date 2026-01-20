import datetime
import logging
import socket
import struct
import time
from typing import List, Tuple

import requests

# ============================================================
# Configuration (edit these)
# ============================================================

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN"

# HyQuery target (the game server must have HyQuery installed/enabled)
HYQUERY_HOST = "example.com"
HYQUERY_PORT = 5520

# What you want displayed in the embed for "Server IP:"
DISPLAY_SERVER_IP = "example.com:5520"

# Embed appearance
EMBED_COLOR = 0x808000  # olive green

# Embed author line (small icon shown in the embed)
EMBED_AUTHOR_NAME = "Hytale"
EMBED_AUTHOR_ICON_URL = "https://example.com/small-icon.png"

# Webhook avatar (the large avatar shown next to the webhook username)
WEBHOOK_AVATAR_URL = "https://example.com/webhook-avatar.png"

# Run every N minutes aligned to the clock (15 => :00, :15, :30, :45)
INTERVAL_MINUTES = 15

# Run one check immediately when the script starts
RUN_ON_STARTUP = True

SOCKET_TIMEOUT_SEC = 3.0


# ============================================================
# HyQuery protocol (FULL query for player list)
# ============================================================

REQ_MAGIC = b"HYQUERY\0"  # 8 bytes
RESP_MAGIC = b"HYREPLY\0"  # 8 bytes

QUERY_TYPE_BASIC = 0x00
QUERY_TYPE_FULL = 0x01


class ParseCursor:
    def __init__(self, start: int = 0) -> None:
        self.pos = start


def _read_u16_le(buf: bytes, cur: ParseCursor) -> int:
    if cur.pos + 2 > len(buf):
        raise ValueError("Read past end while reading uint16")
    (value,) = struct.unpack_from("<H", buf, cur.pos)
    cur.pos += 2
    return int(value)


def _read_u32_le(buf: bytes, cur: ParseCursor) -> int:
    if cur.pos + 4 > len(buf):
        raise ValueError("Read past end while reading uint32")
    (value,) = struct.unpack_from("<I", buf, cur.pos)
    cur.pos += 4
    return int(value)


def _read_bytes(buf: bytes, cur: ParseCursor, count: int) -> bytes:
    if cur.pos + count > len(buf):
        raise ValueError("Read past end while reading bytes")
    out = buf[cur.pos : cur.pos + count]
    cur.pos += count
    return out


def _read_string(buf: bytes, cur: ParseCursor) -> str:
    length = _read_u16_le(buf, cur)
    if length == 0:
        return ""
    data = _read_bytes(buf, cur, length)
    return data.decode("utf-8", errors="replace")


def hyquery_full(
    host: str,
    port: int,
    timeout_sec: float,
) -> Tuple[str, str, int, int, int, str, List[str]]:
    """
    Sends a HyQuery FULL query and parses the reply.

    Returns:
      (server_name, motd, online, max_players, port_in_response, version, player_names)

    Notes:
    - Player list requires HyQuery FULL query (0x01).
    - If the server doesn't have HyQuery installed/enabled, this will time out or fail.
    """
    request = REQ_MAGIC + bytes([QUERY_TYPE_FULL])

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_sec)
        sock.sendto(request, (host, port))
        data, _addr = sock.recvfrom(65535)

    if len(data) < 9:
        raise ValueError("HyQuery response too short")

    if data[:8] != RESP_MAGIC:
        raise ValueError("HyQuery magic mismatch (not a HYREPLY packet)")

    reply_type = data[8]
    if reply_type not in (QUERY_TYPE_BASIC, QUERY_TYPE_FULL):
        raise ValueError(f"Unknown HyQuery reply type: {reply_type:#x}")

    cur = ParseCursor(start=9)

    server_name = _read_string(data, cur)
    motd = _read_string(data, cur)
    online = _read_u32_le(data, cur)
    max_players = _read_u32_le(data, cur)
    port_in_resp = _read_u32_le(data, cur)
    version = _read_string(data, cur)

    player_names: List[str] = []

    if reply_type == QUERY_TYPE_FULL:
        player_count = _read_u32_le(data, cur)
        for _ in range(player_count):
            username = _read_string(data, cur)
            _uuid_raw = _read_bytes(data, cur, 16)  # ignore or store if desired
            player_names.append(username)

        # Plugins section exists in FULL replies; advance cursor for correctness
        plugin_count = _read_u32_le(data, cur)
        for _ in range(plugin_count):
            _plugin_name = _read_string(data, cur)

    return server_name, motd, online, max_players, port_in_resp, version, player_names


# ============================================================
# Discord webhook
# ============================================================

def send_discord_webhook(
    server_name: str,
    online: int,
    max_players: int,
    player_names: List[str],
) -> None:
    if not DISCORD_WEBHOOK_URL or "WEBHOOK_ID" in DISCORD_WEBHOOK_URL:
        logging.error("DISCORD_WEBHOOK_URL is not configured.")
        return

    # Embed field values are limited to 1024 chars
    if player_names:
        player_lines = "\n".join(f"- {name}" for name in player_names)
    else:
        player_lines = "(No names returned)"

    if len(player_lines) > 1024:
        player_lines = player_lines[:1000] + "\n...(truncated)"

    now = datetime.datetime.now(datetime.timezone.utc)

    embed = {
        "color": EMBED_COLOR,
        "author": {
            "name": EMBED_AUTHOR_NAME,
            "icon_url": EMBED_AUTHOR_ICON_URL,
        },
        "description": (
            f"There are {online}/{max_players} online.\n"
            f"Server IP: `{DISPLAY_SERVER_IP}`"
        ),
        "fields": [
            {
                "name": "Players",
                "value": player_lines,
                "inline": False,
            }
        ],
        "timestamp": now.isoformat(),
    }

    payload = {
        # Webhook username = server name
        "username": server_name,
        "avatar_url": WEBHOOK_AVATAR_URL,
        "embeds": [embed],
    }

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code >= 400:
            logging.error("Webhook error %s: %s", resp.status_code, resp.text[:500])
        else:
            logging.info("Webhook sent (%d players).", online)
    except Exception:
        logging.exception("Failed to send webhook")


# ============================================================
# Scheduling
# ============================================================

def seconds_until_next_interval(interval_minutes: int) -> float:
    """
    Seconds until the next interval boundary on the wall clock (local time).
    For interval_minutes=15, runs at :00, :15, :30, :45.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be >= 1")

    now = datetime.datetime.now()
    current_minute = now.minute
    next_minute = ((current_minute // interval_minutes) + 1) * interval_minutes

    target = now.replace(second=0, microsecond=0)

    if next_minute >= 60:
        target = target.replace(minute=0) + datetime.timedelta(hours=1)
    else:
        target = target.replace(minute=next_minute)

    delta = (target - now).total_seconds()
    return max(0.0, float(delta))


def run_check_once() -> None:
    try:
        server_name, motd, online, max_players, port_in_resp, version, player_names = hyquery_full(
            HYQUERY_HOST,
            HYQUERY_PORT,
            SOCKET_TIMEOUT_SEC,
        )

        logging.info(
            "HyQuery OK: name=%r online=%d/%d port=%d version=%r players=%d",
            server_name,
            online,
            max_players,
            port_in_resp,
            version,
            len(player_names),
        )

        if online >= 1:
            send_discord_webhook(server_name, online, max_players, player_names)
        else:
            logging.info("0 players online; no webhook sent.")

    except Exception:
        logging.exception("Check failed")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info("Starting server watcher (runs every %d minutes).", INTERVAL_MINUTES)

    if RUN_ON_STARTUP:
        run_check_once()

    while True:
        sleep_seconds = seconds_until_next_interval(INTERVAL_MINUTES)
        logging.info("Sleeping %.1f seconds until next check.", sleep_seconds)
        time.sleep(sleep_seconds)
        run_check_once()


if __name__ == "__main__":
    main()
