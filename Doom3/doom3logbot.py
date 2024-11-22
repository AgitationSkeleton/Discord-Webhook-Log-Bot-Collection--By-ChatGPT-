import time
import re
import requests
from pathlib import Path
from datetime import datetime
import pytz

# Configuration
LOG_FILE_PATH = r"YOUR_PATH_TO_DOOM3_HERE\d3xp\qconsole.log"
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL_HERE"

# Embed Colors
COLOR_JOIN = 0x00FF00  # Green
COLOR_DISCONNECT = 0xFF0000  # Red
COLOR_CHAT = 0xFFFFFF  # White

# Invalid Player Names
INVALID_PLAYER_NAMES = [
    "Strings", "Statements", "Functions", "Variables", "Mem used", 
    "Static data", "Allocated", "Thread size", "SpawnPlayer", "WARNING",
    "glprogs/heatHazeWithMask.vfpWARNING", "Map"
]

# Message Patterns
JOIN_PATTERN = re.compile(r"^Server: (.+?) joined the game\.$")
CHAT_PATTERN = re.compile(r"^([^:]+): (.+)$")  # Capture player name and message
DISCONNECT_PATTERN = re.compile(r"^(.+?) disconnected\.$")

# Define PST timezone
pst = pytz.timezone('US/Pacific')

def is_invalid_player_name(player_name):
    """Check if the player name is in the invalid player names list."""
    for invalid_name in INVALID_PLAYER_NAMES:
        if invalid_name in player_name:
            return True
    return False

def get_timestamp():
    """Get the current timestamp in ISO format for PST time zone."""
    return datetime.now(pst).isoformat()

def send_to_discord(username, message, color):
    """Send a message to Discord with rate limit handling."""
    timestamp = get_timestamp()  # Get timestamp for each message
    embed = {
        "title": username,
        "description": message,
        "color": color,
        "timestamp": timestamp  # Add timestamp to the embed
    }
    payload = {"embeds": [embed]}
    
    while True:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code == 429:  # Rate limit exceeded
            retry_after = response.json().get('retry_after', 1)
            print(f"Rate limit hit, retrying after {retry_after} seconds.")
            time.sleep(retry_after)
        elif response.status_code == 204:
            print(f"Message sent to Discord: {username}: {message}")
            break
        else:
            print(f"Failed to send message: {response.status_code}, {response.text}")
            break

def monitor_log(file_path):
    """Monitor the log file for changes."""
    file_path = Path(file_path)
    last_size = file_path.stat().st_size

    while True:
        current_size = file_path.stat().st_size
        if current_size < last_size:  # Log file reset
            print("Log file reset detected.")
            last_size = 0

        if current_size > last_size:
            with file_path.open("r", encoding="utf-8") as file:
                file.seek(last_size)  # Start from the last read position
                for line in file:
                    line = line.strip()  # Strip leading/trailing whitespace
                    
                    # Match join messages and skip invalid player names
                    if match := JOIN_PATTERN.match(line):
                        username = match.group(1)
                        if is_invalid_player_name(username):
                            continue
                        send_to_discord(username, "joined the game.", COLOR_JOIN)
                    
                    # Match chat messages and skip invalid player names
                    elif match := CHAT_PATTERN.match(line):
                        username, message = match.groups()
                        if is_invalid_player_name(username):
                            continue
                        if message.strip():  # Ensure there is a message after the colon
                            send_to_discord(username, message, COLOR_CHAT)
                        else:
                            print(f"Empty message detected for user: {username}")
                    
                    # Match disconnect messages and skip invalid player names
                    elif match := DISCONNECT_PATTERN.match(line):
                        username = match.group(1)
                        if is_invalid_player_name(username):
                            continue
                        send_to_discord(username, "left the game.", COLOR_DISCONNECT)

            last_size = current_size

        time.sleep(1)

if __name__ == "__main__":
    monitor_log(LOG_FILE_PATH)
