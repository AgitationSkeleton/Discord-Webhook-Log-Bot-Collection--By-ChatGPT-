import time
import re
import requests
from pathlib import Path

# Configuration
LOG_FILE_PATH = r"YOUR_PATH_TO_QL_HERE\quakelive\baseq3\qconsole.log"
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL_HERE"
IGNORE_LIST_FILE = "ignore_list.txt"

# Embed Colors
COLOR_JOIN = 0x00FF00  # Green
COLOR_DISCONNECT = 0xFF0000  # Red
COLOR_CHAT = 0xFFFFFF  # White

# Patterns
STEAM_ID_PATTERN = re.compile(r"(.+?) connected with Steam ID (\d+)")
CHAT_PATTERN = re.compile(r"(.+?)\^7: (.+)")
DISCONNECT_PATTERN = re.compile(r'broadcast: print "(.+?) disconnected\\n"')

def load_ignore_list(file_path):
    """Load names to ignore from a text file."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            ignore_list = {line.strip().lower() for line in file if line.strip()}
            print(f"Ignoring messages from: {ignore_list}")
            return ignore_list
    except FileNotFoundError:
        print(f"Ignore list file '{file_path}' not found. Proceeding without it.")
        return set()

def sanitize_text(text):
    """Remove color codes (e.g., ^1, ^2, etc.) and trim whitespace."""
    return re.sub(r"\^\d", "", text).strip()

def send_to_discord(message, color, username=None):
    """Send a message to Discord."""
    embed = {"color": color}
    if username:
        embed["author"] = {"name": username}
        embed["description"] = message
    else:
        embed["description"] = message
    payload = {"embeds": [embed]}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if response.status_code == 204:
        print(f"Sent: {message}")
    else:
        print(f"Failed to send message: {response.status_code}, {response.text}")

def monitor_log(file_path, ignore_list):
    """Monitor the log file for relevant events."""
    file_path = Path(file_path)
    last_size = file_path.stat().st_size

    while True:
        current_size = file_path.stat().st_size
        if current_size < last_size:  # Log file reset
            print("Log file reset detected.")
            last_size = 0

        if current_size > last_size:
            with file_path.open("r", encoding="utf-8") as file:
                file.seek(last_size)
                for line in file:
                    line = line.strip()
                    
                    # Player join with Steam ID
                    if match := STEAM_ID_PATTERN.search(line):
                        username, steam_id = match.groups()
                        username = sanitize_text(username)
                        if username.lower() not in ignore_list:
                            send_to_discord(
                                f"{line}",
                                COLOR_JOIN
                            )
                    
                    # Player chat message
                    elif match := CHAT_PATTERN.search(line):
                        username, message = match.groups()
                        username = sanitize_text(username)
                        message = sanitize_text(message)
                        if username.lower() not in ignore_list:
                            send_to_discord(
                                message,
                                COLOR_CHAT,
                                username=username
                            )
                    
                    # Player disconnects (explicit pattern match)
                    elif match := DISCONNECT_PATTERN.search(line):
                        username = sanitize_text(match.group(1))
                        if username.lower() not in ignore_list:
                            send_to_discord(
                                f"{username} disconnected",
                                COLOR_DISCONNECT
                            )

            last_size = current_size

        time.sleep(1)

if __name__ == "__main__":
    ignore_list = load_ignore_list(IGNORE_LIST_FILE)
    monitor_log(LOG_FILE_PATH, ignore_list)
