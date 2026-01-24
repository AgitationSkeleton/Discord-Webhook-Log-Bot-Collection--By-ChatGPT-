import datetime
import logging
import socket
import struct
import threading
import time
import random
import io
from typing import List, Tuple, Optional

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
# Optional: GameSpy4 / "Minecraft query" UDP bridge
# ============================================================
#
# Purpose:
#   Tools like GameTracker/GameDig can query Minecraft servers using the old
#   GameSpy4 UDP protocol (0xFE 0xFD handshake + stat). Hytale doesn't speak
#   this protocol, so this script can optionally expose a *separate* UDP port
#   (default 5521) that replies in Minecraft's GameSpy4 format using data
#   pulled from HyQuery.
#
# Notes:
#   - This does NOT change how the script queries Hytale (still HyQuery).
#   - It also does NOT replace the Discord watcher behavior.
#   - If you don't need the bridge, set BRIDGE_ENABLED = False.

BRIDGE_ENABLED = True
BRIDGE_BIND_HOST = "0.0.0.0"
BRIDGE_LISTEN_PORT = 5521

# How often to refresh cached HyQuery data for the bridge.
# (Querying on every inbound UDP packet would also work, but caching makes
# bursty tool queries cheaper.)
BRIDGE_REFRESH_SECONDS = 10.0

# Values used to make the response look Minecraft-like
BRIDGE_GAME_TYPE = "SMP"
BRIDGE_GAME_ID = "MINECRAFT"
BRIDGE_MAP_NAME = "world"
BRIDGE_PLUGINS_STRING = "HytaleQueryBridge"

# Optional overrides (off by default)
BRIDGE_OVERRIDE_HOSTNAME_ENABLED = False
BRIDGE_OVERRIDE_HOSTNAME = "Hytale Server"

BRIDGE_OVERRIDE_MAP_ENABLED = False
BRIDGE_OVERRIDE_MAP_NAME = "world"


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
# GameSpy4 / "Minecraft query" bridge implementation
# ============================================================

class BridgeCache:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_ok_utc: float = 0.0
        self.server_name: str = ""
        self.motd: str = ""
        self.online: int = 0
        self.max_players: int = 0
        self.port_in_resp: int = 0
        self.version: str = ""
        self.player_names: List[str] = []
        self.last_error: str = ""


def _resolve_ipv4_string(hostname: str) -> str:
    try:
        addrs = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM)
        if addrs:
            return str(addrs[0][4][0])
    except Exception:
        pass
    return "127.0.0.1"


def _parse_display_hostport(display_server_ip: str) -> Tuple[str, int]:
    # Best-effort parse for "host:port"; if it doesn't match, fall back.
    if ":" in display_server_ip:
        host_part, port_part = display_server_ip.rsplit(":", 1)
        try:
            return host_part.strip(), int(port_part.strip())
        except Exception:
            return display_server_ip.strip(), 0
    return display_server_ip.strip(), 0


def _write_ascii(out: io.BytesIO, text: str) -> None:
    out.write(text.encode("utf-8", errors="replace"))


def _build_gamespy_handshake_reply(session_id: int, challenge_token: int) -> bytes:
    # 0x09 + session_id (int32 BE) + token ASCII + null
    token_ascii = str(challenge_token).encode("ascii")
    return struct.pack(">Bi", 0x09, session_id) + token_ascii + b"\x00"


def _build_gamespy_fullstat_reply(
    session_id: int,
    hostname: str,
    version: str,
    map_name: str,
    num_players: int,
    max_players: int,
    host_port: int,
    host_ip: str,
    player_names: List[str],
) -> bytes:
    out = io.BytesIO()

    # Header
    out.write(struct.pack(">Bi", 0x00, session_id))

    # splitnum\0 0x80 0x00
    _write_ascii(out, "splitnum")
    out.write(b"\x00\x80\x00")

    # Key/value pairs (ASCII, null-separated)
    def kv(k: str, v: str) -> None:
        _write_ascii(out, k)
        out.write(b"\x00")
        _write_ascii(out, v)
        out.write(b"\x00")

    kv("hostname", hostname)
    kv("gametype", BRIDGE_GAME_TYPE)
    kv("game_id", BRIDGE_GAME_ID)
    kv("version", version)
    kv("plugins", BRIDGE_PLUGINS_STRING)
    kv("map", map_name)
    kv("numplayers", str(num_players))
    kv("maxplayers", str(max_players))
    kv("hostport", str(host_port))
    kv("hostip", host_ip)

    # End of key/value section
    out.write(b"\x00")

    # Player section
    out.write(b"\x01")
    _write_ascii(out, "player_")
    out.write(b"\x00\x00")
    for name in player_names:
        _write_ascii(out, name)
        out.write(b"\x00")

    # Two nulls at the end (matches modern servers)
    out.write(b"\x00\x00")
    return out.getvalue()


class HyQueryPoller(threading.Thread):
    def __init__(self, cache: BridgeCache) -> None:
        super().__init__(daemon=True)
        self.cache = cache
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                server_name, motd, online, max_players, port_in_resp, version, player_names = hyquery_full(
                    HYQUERY_HOST,
                    HYQUERY_PORT,
                    SOCKET_TIMEOUT_SEC,
                )

                with self.cache.lock:
                    self.cache.last_ok_utc = time.time()
                    self.cache.server_name = server_name
                    self.cache.motd = motd
                    self.cache.online = online
                    self.cache.max_players = max_players
                    self.cache.port_in_resp = port_in_resp
                    self.cache.version = version
                    self.cache.player_names = list(player_names)
                    self.cache.last_error = ""
            except Exception as e:
                with self.cache.lock:
                    self.cache.last_error = str(e)
            finally:
                self._stop_event.wait(BRIDGE_REFRESH_SECONDS)


class GameSpyQueryBridge(threading.Thread):
    def __init__(self, cache: BridgeCache) -> None:
        super().__init__(daemon=True)
        self.cache = cache
        self._stop_event = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._session_tokens: dict[int, int] = {}
        self._session_lock = threading.Lock()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    def _get_or_create_token(self, session_id: int) -> int:
        with self._session_lock:
            token = self._session_tokens.get(session_id)
            if token is None:
                token = random.randint(1, 0x7FFFFFFF)
                self._session_tokens[session_id] = token
            return token

    def run(self) -> None:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.bind((BRIDGE_BIND_HOST, BRIDGE_LISTEN_PORT))
            self._sock.settimeout(0.5)
        except Exception:
            logging.exception("Bridge: failed to bind UDP/%d", BRIDGE_LISTEN_PORT)
            return

        logging.info("Bridge: listening for GameSpy4 query on %s:%d", BRIDGE_BIND_HOST, BRIDGE_LISTEN_PORT)

        display_host, display_port = _parse_display_hostport(DISPLAY_SERVER_IP)
        host_ip = _resolve_ipv4_string(display_host)
        host_port = display_port if display_port > 0 else HYQUERY_PORT

        while not self._stop_event.is_set():
            try:
                data, addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                # Expect: 0xFE 0xFD <type> <sessionId(4)> ...
                if len(data) < 7 or data[0] != 0xFE or data[1] != 0xFD:
                    continue

                req_type = data[2]
                session_id = struct.unpack(">i", data[3:7])[0]

                if req_type == 0x09:
                    token = self._get_or_create_token(session_id)
                    resp = _build_gamespy_handshake_reply(session_id, token)
                    self._sock.sendto(resp, addr)
                    continue

                if req_type == 0x00:
                    with self.cache.lock:
                        hostname = self.cache.server_name or "Hytale Server"
                        version = self.cache.version or "Hytale"
                        num_players = int(self.cache.online)
                        max_players = int(self.cache.max_players)
                        players = list(self.cache.player_names)

                    # Optional overrides (off by default)
                    if BRIDGE_OVERRIDE_HOSTNAME_ENABLED:
                        hostname = BRIDGE_OVERRIDE_HOSTNAME

                    map_name = BRIDGE_MAP_NAME
                    if BRIDGE_OVERRIDE_MAP_ENABLED:
                        map_name = BRIDGE_OVERRIDE_MAP_NAME


                    resp = _build_gamespy_fullstat_reply(
                        session_id=session_id,
                        hostname=hostname,
                        version=version,
                        map_name=map_name,
                        num_players=num_players,
                        max_players=max_players,
                        host_port=host_port,
                        host_ip=host_ip,
                        player_names=players,
                    )
                    self._sock.sendto(resp, addr)
                    continue

            except Exception:
                # Never let a bad packet crash the bridge.
                logging.debug("Bridge: failed to handle packet", exc_info=True)



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

    # Start the optional GameSpy4 bridge (separate UDP port) without affecting
    # the Discord watcher behavior.
    bridge_cache: Optional[BridgeCache] = None
    poller: Optional[HyQueryPoller] = None
    bridge: Optional[GameSpyQueryBridge] = None
    if BRIDGE_ENABLED:
        bridge_cache = BridgeCache()
        poller = HyQueryPoller(bridge_cache)
        bridge = GameSpyQueryBridge(bridge_cache)
        poller.start()
        bridge.start()

    if RUN_ON_STARTUP:
        run_check_once()

    try:
        while True:
            sleep_seconds = seconds_until_next_interval(INTERVAL_MINUTES)
            logging.info("Sleeping %.1f seconds until next check.", sleep_seconds)
            time.sleep(sleep_seconds)
            run_check_once()
    except KeyboardInterrupt:
        logging.info("Stopping...")
    finally:
        if bridge is not None:
            bridge.stop()
        if poller is not None:
            poller.stop()


if __name__ == "__main__":
    main()
