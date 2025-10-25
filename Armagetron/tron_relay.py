#!/usr/bin/env python3
import os, time, json, re
from urllib import request, error

# ====== CONFIG ======
LOG_PATH = r"C:\Program Files (x86)\Armagetron Sty+CT Dedicated\logs\server_console.log"
WEBHOOK_URL = "URL"
SERVER_NAME = "Retrocycles"

POST_JOINS  = True
POST_LEAVES = True
POST_CHAT   = True

START_AT_END       = False
REPLAY_TAIL_KB     = 64
STARTUP_TEST_POST  = True
PRINT_MATCHES      = True
PRINT_DIAG         = True

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
IGNORE_FILE = os.path.join(SCRIPT_DIR, "ignored_names.txt")
# =====================

# Regexes (case-insensitive) — capture ID where available
JOIN_RE   = re.compile(r'^\[(\d+)\]\s+(.+?)\s+entered the game\.?\s*$', re.I)
LEAVE_RE  = re.compile(r'^\[(\d+)\]\s+(.+?)\s+left the game\.?\s*$',   re.I)
CHAT_RE   = re.compile(r'^\[(\d+)\]\s+(.+?)\:\s(.*)$',                  re.I)

# Logout variants without a name (use ID->name map)
LOGOUT_RE = re.compile(r'^\[(\d+)\]\s+received logout from\s+(\d+)\.?', re.I)
KILLING_RE= re.compile(r'^\[(\d+)\]\s+Killing user\s+(\d+)\b',          re.I)

# Heuristic: words that mark a system line, not a player name
SYSTEM_TOKENS = {
    "received", "login", "socket", "network", "version", "id",
    "closing", "bound", "ping", "timestamp", "creating", "syncing",
    "relabeling", "sending", "logging", "error", "downloading",
    "resource", "master", "done", "nobody", "charity", "poll"
}

_ignore_names = set()
_ignore_mtime = None
_detected_encoding = None  # "utf-8" or "utf-16-le"

# Track current user ids -> names (best-effort)
uid_to_name = {}

def _post_discord(content: str):
    payload = {"content": content[:1900]}
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ArmagetronRelay/1.0 (+https://redchanit.xyz) Python-urllib",
    }
    req = request.Request(WEBHOOK_URL, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=10) as resp:
            return
    except error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            body = ""
        print(f"[relay] HTTPError {e.code}: {body[:500]}")
        if e.code == 429:
            time.sleep(2.5)
    except Exception as ex:
        print(f"[relay] Error posting to Discord: {ex}")

def _sanitize_name(s: str) -> str:
    return s.strip().replace("@", "@\u200b")

def _sanitize_msg(s: str) -> str:
    return s.strip().replace("@", "@\u200b")

def _load_ignore():
    global _ignore_names, _ignore_mtime
    try:
        mtime = os.path.getmtime(IGNORE_FILE)
    except OSError:
        if _ignore_names and PRINT_DIAG:
            print("[relay] ignored_names.txt missing; clearing ignore list")
        _ignore_names = set()
        _ignore_mtime = None
        return
    if _ignore_mtime is None or mtime != _ignore_mtime:
        names = set()
        try:
            with open(IGNORE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    t = line.strip()
                    if t and not t.startswith("#"):
                        names.add(t.lower())
        except Exception as ex:
            print(f"[relay] Could not read ignored_names.txt: {ex}")
            names = set()
        _ignore_names = names
        _ignore_mtime = mtime
        print(f"[relay] Loaded {len(_ignore_names)} ignored names")

def _is_ignored(name: str) -> bool:
    _load_ignore()
    return name.strip().lower() in _ignore_names

# ---------- decoding helpers (UTF-8 vs UTF-16LE) ----------
def _guess_encoding(sample: bytes) -> str:
    if sample.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if sample.startswith(b"\xfe\xff"):
        return "utf-16-be"  # unlikely here
    nul_ratio = sample.count(b"\x00") / max(1, len(sample))
    return "utf-16-le" if nul_ratio > 0.2 else "utf-8"

def _decode_line(b: bytes) -> str:
    global _detected_encoding
    if _detected_encoding is None:
        _detected_encoding = _guess_encoding(b)
        if PRINT_DIAG:
            print(f"[relay] Detected encoding: {_detected_encoding}")
    try:
        s = b.decode(_detected_encoding, errors="ignore")
    except Exception:
        alt = "utf-8" if _detected_encoding != "utf-8" else "utf-16-le"
        try:
            s = b.decode(alt, errors="ignore")
            _detected_encoding = alt
            if PRINT_DIAG:
                print(f"[relay] Switched encoding to: {_detected_encoding}")
        except Exception:
            s = b.decode("utf-8", errors="ignore")
    s = s.replace("\r", "").replace("\n", "")
    s = "".join(ch for ch in s if ch == "\t" or ord(ch) >= 0x20)
    return s
# ----------------------------------------------------------

def _looks_like_system_name(raw_before_colon: str) -> bool:
    # Heuristic: if the would-be "name" contains digits/dots (IPs/ports) or system tokens, skip
    test = raw_before_colon.lower()
    if any(c.isdigit() for c in test) or "." in test:
        return True
    for tok in SYSTEM_TOKENS:
        if f" {tok} " in f" {test} ":
            return True
    return False

def _handle_line(line: str):
    # JOIN (captures id and name)
    m = JOIN_RE.match(line)
    if m and POST_JOINS:
        uid, name = m.group(1), m.group(2).strip()
        uid_to_name[uid] = name
        if _is_ignored(name):
            if PRINT_MATCHES: print(f"[relay] (ignored join) {name}")
            return
        if PRINT_MATCHES: print(f"[relay] JOIN  -> [{uid}] {name}")
        _post_discord(f"[{SERVER_NAME}] + {_sanitize_name(name)} entered the game")
        return
    elif "entered the game" in line.lower() and PRINT_DIAG:
        print(f"[relay] DIAG: join candidate not matched: {repr(line)}")

    # LEAVE (named form)
    m = LEAVE_RE.match(line)
    if m and POST_LEAVES:
        uid, name = m.group(1), m.group(2).strip()
        uid_to_name.pop(uid, None)
        if _is_ignored(name):
            if PRINT_MATCHES: print(f"[relay] (ignored leave) {name}")
            return
        if PRINT_MATCHES: print(f"[relay] LEAVE -> [{uid}] {name}")
        _post_discord(f"[{SERVER_NAME}] - {_sanitize_name(name)} left the game")
        return

    # Logout/kill forms without name — use ID mapping
    m = LOGOUT_RE.match(line) or KILLING_RE.match(line)
    if m and POST_LEAVES:
        _, victim_id = m.groups()
        name = uid_to_name.pop(victim_id, f"User {victim_id}")
        if not _is_ignored(name):
            if PRINT_MATCHES: print(f"[relay] LEAVE -> [{victim_id}] {name} (by logout/kill)")
            _post_discord(f"[{SERVER_NAME}] - {_sanitize_name(name)} left the game")
        else:
            if PRINT_MATCHES: print(f"[relay] (ignored leave) [{victim_id}] {name}")
        return

    # CHAT — reject if the would-be "name" segment smells like a system line
    m = CHAT_RE.match(line)
    if m and POST_CHAT:
        uid, raw_name, msg = m.groups()
        if _looks_like_system_name(raw_name):
            if PRINT_DIAG: print(f"[relay] DIAG: rejected system-ish chat: {repr(line)}")
            return
        uid_to_name[uid] = raw_name.strip() or uid_to_name.get(uid, raw_name)
        if _is_ignored(raw_name):
            if PRINT_MATCHES: print(f"[relay] (ignored chat) {raw_name}: {msg}")
            return
        if PRINT_MATCHES: print(f"[relay] CHAT  -> [{uid}] {raw_name}: {msg}")
        _post_discord(f"[{SERVER_NAME}] {_sanitize_name(raw_name)}: {_sanitize_msg(msg)}")
        return
    elif line.startswith("[") and ":" in line and PRINT_DIAG:
        print(f"[relay] DIAG: chat candidate not matched: {repr(line)}")

def _open_and_seek(path: str):
    fh = open(path, "rb")
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if START_AT_END:
        fh.seek(0, os.SEEK_END)
    else:
        if size > REPLAY_TAIL_KB * 1024:
            fh.seek(-REPLAY_TAIL_KB * 1024, os.SEEK_END)
            fh.readline()
        else:
            fh.seek(0, os.SEEK_SET)
    return fh

def _tail_follow(path: str):
    global _detected_encoding
    fh = None
    last_inode = None
    while True:
        try:
            if fh is None:
                _detected_encoding = None
                fh = _open_and_seek(path)
                try:
                    last_inode = os.stat(path).st_ino
                except Exception:
                    last_inode = None

            where = fh.tell()
            bline = fh.readline()
            if bline:
                line = _decode_line(bline)
                if line:
                    _handle_line(line)
                continue

            try:
                st = os.stat(path)
                rotated = (last_inode is not None and st.st_ino != last_inode)
                truncated = (where > st.st_size)
                if rotated or truncated:
                    if PRINT_MATCHES:
                        print("[relay] log rotated or truncated; reopening")
                    fh.close()
                    fh = None
                    continue
            except FileNotFoundError:
                if fh:
                    fh.close()
                    fh = None
            time.sleep(0.2)

        except FileNotFoundError:
            time.sleep(0.5)
        except Exception as ex:
            print(f"[relay] Tail error: {ex}")
            time.sleep(0.5)

if __name__ == "__main__":
    print(f"[relay] Watching: {LOG_PATH}")
    _load_ignore()
    if STARTUP_TEST_POST:
        _post_discord(f"[{SERVER_NAME}] relay online (startup test)")
    _tail_follow(LOG_PATH)
