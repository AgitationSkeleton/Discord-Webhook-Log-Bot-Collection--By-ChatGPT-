import re
import time
import requests
from pathlib import Path

# Path to server.log
LOG_PATH = Path(r"path_to_\server.log")

# Discord webhook URL
WEBHOOK_URL = "your webhook here"

# Color codes
EMBED_COLORS = {
    "join": 0x00FF00,      # Green
    "leave": 0xFF0000,     # Red
    "chat": 0xFFFFFF       # White
}

# Patterns
JOIN_PATTERN = re.compile(r"\[INFO\] (?P<name>\w+) \[\/[\d.:]+\] logged in with entity id \d+ at")
LEAVE_PATTERN = re.compile(r"\[INFO\] (?P<name>\w+) lost connection: (?P<reason>.+)")
CHAT_PATTERN = re.compile(r"\[INFO\] <(?P<name>\w+)> (?P<message>.+)")
CMD_PATTERN = re.compile(r"\[INFO\] (?P<name>\w+) issued server command: (?P<servercmd>.+)")

def get_avatar_url(username):
    return f"https://minotar.net/helm/{username}/64.png"

def send_discord_embed(username, description, color):
    avatar_url = get_avatar_url(username)
    embed = {
        "embeds": [{
            "title": username,
            "description": description,
            "color": color,
            "thumbnail": {"url": avatar_url}
        }]
    }
    try:
        requests.post(WEBHOOK_URL, json=embed)
    except Exception as e:
        print(f"Failed to send message: {e}")

def follow(file):
    """Generator to yield new lines as they are written."""
    file.seek(0, 2)  # Go to end of file
    while True:
        line = file.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line

def parse_log():
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        log_lines = follow(f)
        for line in log_lines:
            if match := JOIN_PATTERN.search(line):
                name = match.group("name")
                send_discord_embed(name, "joined the game", EMBED_COLORS["join"])

            elif match := LEAVE_PATTERN.search(line):
                name = match.group("name")
                reason = match.group("reason")
                send_discord_embed(name, f"left the game ({reason})", EMBED_COLORS["leave"])

            elif match := CHAT_PATTERN.search(line):
                name = match.group("name")
                message = match.group("message")
                send_discord_embed(name, message, EMBED_COLORS["chat"])
                
            elif match := CMD_PATTERN.search(line):
                name = match.group("name")
                servercmd = match.group("servercmd")
                send_discord_embed(name, f"issued server command: ({servercmd})", EMBED_COLORS["chat"])                

if __name__ == "__main__":
    print("Watching log file for events...")
    parse_log()