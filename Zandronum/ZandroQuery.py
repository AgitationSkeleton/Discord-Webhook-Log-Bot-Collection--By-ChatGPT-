import datetime
import logging
import socket
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

# =========================================
# Configuration
# =========================================

# Discord webhook URL
# Replace this with your actual Discord webhook URL.
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your_webhook_id/your_token"

# doomlist API endpoint for Zandronum servers
DOOMLIST_API_URL = "https://doomlist.net/api/full"

# How often to run: every 15 minutes on the clock (00, 15, 30, 45)
CHECK_INTERVAL_MINUTES = 15

# Zandronum servers to monitor.
# Each entry:
#   label       - Friendly human-readable label to show in the embed.
#   dns         - Hostname players use to connect (for display).
#   fallback_ip - IP to fall back to if DNS resolution fails.
#   port        - Server port.
ZANDRONUM_SERVERS = [
    {
        "label": "Example Doom Server 1",
        "dns": "example.doomserver.net",
        "fallback_ip": "203.0.113.42",
        "port": 10666,
    },
    {
        "label": "Example Doom Server 2",
        "dns": "example.doomserver.net",
        "fallback_ip": "203.0.113.42",
        "port": 10667,
    },
    # Add more servers here as needed...
]


# =========================================
# Helper functions
# =========================================

def resolve_dns(hostname: str) -> Optional[str]:
    """Resolve a hostname to an IPv4 address, or return None on failure."""
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        logging.warning("DNS resolution failed for %s", hostname)
        return None


def fetch_doomlist_data() -> Dict[str, Any]:
    """Fetch the doomlist JSON data and return it as a dict."""
    response = requests.get(DOOMLIST_API_URL, timeout=10)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected doomlist API format (expected JSON object)")
    return data


def find_zandronum_server(
    doomlist_data: Dict[str, Any],
    dns_name: str,
    fallback_ip: str,
    port: int,
) -> Optional[Dict[str, Any]]:
    """
    Try to find a Zandronum server entry in doomlist for the given host/port.

    Resolution strategy:
    1. Resolve the DNS name to an IP and look for "ip:port" in doomlist.
    2. If that fails, look for "fallback_ip:port".
    3. As a last resort, scan all entries looking for a matching IP and port.
    """
    resolved_ip = resolve_dns(dns_name)
    candidate_ips: List[str] = []
    if resolved_ip:
        candidate_ips.append(resolved_ip)
    if fallback_ip not in candidate_ips:
        candidate_ips.append(fallback_ip)

    # First, try direct key lookup "ip:port"
    for ip in candidate_ips:
        key = f"{ip}:{port}"
        if key in doomlist_data:
            return doomlist_data[key]

    # Fallback: scan values in case doomlist changes its key format
    for server_info in doomlist_data.values():
        try:
            addr = server_info.get("addr")
            server_port = int(server_info.get("port"))
        except Exception:
            continue

        if server_port == port and addr in candidate_ips:
            return server_info

    return None


def get_player_counts(server_info: Dict[str, Any]) -> Tuple[int, int, List[str]]:
    """
    Returns (num_playing, num_spectating, human_names).

    - Counts only non-bot players as humans.
    - Spectators are counted separately but still included in the total human count.
    - If detailed player data is missing, falls back to approximate counts
      from numplaying or numplayers and returns an empty name list.
    """
    player_data = server_info.get("playerdata")
    if not player_data:
        approx = server_info.get("numplaying")
        if approx is None:
            approx = server_info.get("numplayers", 0)
        try:
            approx_int = int(approx)
        except Exception:
            approx_int = 0
        # No player detail available, treat them all as playing.
        return approx_int, 0, []

    num_playing = 0
    num_spectating = 0
    human_names: List[str] = []

    for player in player_data:
        if player.get("bot"):
            # Ignore bots for human counts
            continue

        plain_name = player.get("plain-name") or player.get("name") or "Unknown"
        if player.get("spec"):
            num_spectating += 1
        else:
            num_playing += 1
        human_names.append(plain_name)

    return num_playing, num_spectating, human_names


def build_zandronum_embed(
    server_meta: Dict[str, Any],
    server_info: Dict[str, Any],
    num_playing: int,
    num_spectating: int,
    human_names: List[str],
) -> Tuple[Dict[str, Any], str]:
    """
    Build the Discord embed payload for a Zandronum server.

    Returns:
        (embed_dict, webhook_username)

    webhook_username is taken from the server's hostname (Zandronum cvar,
    e.g. in doomlist "hostname"), with fallback to the friendly label.
    """
    server_label = server_meta["label"]
    dns_name = server_meta["dns"]
    port = server_meta["port"]

    game_name = server_info.get("gamename", "Unknown")
    map_name = server_info.get("mapname", "Unknown")
    addr_ip = server_info.get("addr", "Unknown")

    max_players = (
        server_info.get("maxplayers")
        or server_info.get("maxclients")
        or "?"
    )

    total_humans = num_playing + num_spectating

    if human_names:
        player_list_value = "\n".join(f"- {name}" for name in human_names)
    else:
        player_list_value = "(none)"

    hostname = server_info.get("hostname") or server_info.get("name") or server_label

    embed = {
        "title": "Doom Server Status",
        "color": 0x00FF00,  # Green: at least one human connected
        "fields": [
            {
                "name": "Name",
                "value": server_label,
                "inline": False,
            },
            {
                "name": "Hostname",
                "value": hostname,
                "inline": False,
            },
            {
                "name": "Address",
                "value": f"{dns_name}:{port}",
                "inline": True,
            },
            {
                "name": "IP (resolved)",
                "value": f"{addr_ip}:{port}",
                "inline": True,
            },
            {
                "name": "Game",
                "value": game_name,
                "inline": True,
            },
            {
                "name": "Map",
                "value": map_name,
                "inline": True,
            },
            {
                "name": "Players",
                "value": f"{total_humans} / {max_players}",
                "inline": True,
            },
            {
                "name": "Spectators",
                "value": str(num_spectating),
                "inline": True,
            },
            {
                "name": "Player List",
                "value": player_list_value,
                "inline": False,
            },
        ],
    }

    return embed, hostname


def send_discord_webhook(embed: Dict[str, Any], username: Optional[str] = None) -> None:
    """
    Send a single Discord webhook message containing the given embed.

    If username is provided, the webhook's display name will be set to it.
    """
    if not DISCORD_WEBHOOK_URL or "your_webhook_id" in DISCORD_WEBHOOK_URL:
        logging.error("DISCORD_WEBHOOK_URL is not configured.")
        return

    payload: Dict[str, Any] = {
        "content": "",
        "embeds": [embed],
    }

    if username:
        payload["username"] = username

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        if response.status_code >= 400:
            logging.error(
                "Webhook error %s: %s",
                response.status_code,
                response.text[:500],
            )
    except Exception as e:
        logging.exception("Failed to send webhook: %s", e)


# =========================================
# Scheduling
# =========================================

def seconds_until_next_quarter() -> float:
    """
    Returns the number of seconds until the next time the minutes are
    a multiple of 15 (00, 15, 30, 45), with seconds == 0.
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
    if delta < 0:
        delta = 0
    return delta


def run_check_once() -> None:
    """
    Single pass:
    - Fetch doomlist.
    - For each configured Zandronum server, if total humans (players + spectators) > 0,
      send a Discord webhook with details.
    """
    logging.info("Running server check...")

    try:
        doomlist_data = fetch_doomlist_data()
    except Exception as e:
        logging.error("Failed to fetch doomlist data: %s", e)
        return

    for server_meta in ZANDRONUM_SERVERS:
        try:
            server_info = find_zandronum_server(
                doomlist_data=doomlist_data,
                dns_name=server_meta["dns"],
                fallback_ip=server_meta["fallback_ip"],
                port=server_meta["port"],
            )

            if not server_info:
                logging.info("Server not found in doomlist: %s", server_meta["label"])
                continue

            num_playing, num_spectating, human_names = get_player_counts(server_info)
            total_humans = num_playing + num_spectating

            if total_humans > 0:
                embed, hostname = build_zandronum_embed(
                    server_meta,
                    server_info,
                    num_playing,
                    num_spectating,
                    human_names,
                )
                send_discord_webhook(embed, username=hostname)
                logging.info(
                    "Sent webhook for server %s with %d humans (playing %d, spectating %d).",
                    server_meta["label"],
                    total_humans,
                    num_playing,
                    num_spectating,
                )
            else:
                logging.info(
                    "Server %s has 0 humans connected; no webhook sent.",
                    server_meta["label"],
                )
        except Exception as e:
            logging.exception(
                "Error handling server %s: %s",
                server_meta["label"],
                e,
            )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logging.info("Starting generic Doom server status bot.")

    # Immediate check on startup
    logging.info("Running initial check on startup...")
    run_check_once()

    # Then continue on the regular quarter-hour cadence
    while True:
        sleep_seconds = seconds_until_next_quarter()
        logging.info(
            "Sleeping %.1f seconds until next quarter-hour check.",
            sleep_seconds,
        )
        time.sleep(sleep_seconds)
        run_check_once()


if __name__ == "__main__":
    main()
