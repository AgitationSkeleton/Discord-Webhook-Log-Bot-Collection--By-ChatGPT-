import time
import re
import requests
from pathlib import Path
from datetime import datetime
from pytz import timezone

# Configuration
LOG_FILE_PATH = r"YOUR_PATH_TO_MURMUR_LOGS_HERE\\AppData\\Local\\Mumble\\Murmur\\mumble-server.log"
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL_HERE"
LOCAL_TIMEZONE = timezone("US/Pacific")  # Assume the log timestamps are PST

# Embed Colors
COLOR_JOIN = 0x00FF00  # Green
COLOR_DISCONNECT = 0xFF0000  # Red
COLOR_CHAT = 0xFFFFFF  # White
CHANNEL_COLORS = {
    "Red": 0xFF0000,
    "Blue": 0x0000FF,
    "Green": 0x00FF00,
    "Yellow": 0xFFFF00,
    "Root": 0xAAAAAA  # Gray for Root channel
}

# Message Patterns
NEW_CONNECTION_PATTERN = re.compile(r"New connection: ([\d.]+):\d+")
AUTHENTICATION_PATTERN = re.compile(r"<\d+:(.+?)\(\d+\)> Authenticated")
CHANNEL_CHANGE_PATTERN = re.compile(r"<\d+:(.+?)\(\d+\)> Moved .+ to (.+?)\[")
DISCONNECT_PATTERN = re.compile(r"<\d+:(.+?)\(\d+\)> Connection closed")

def send_to_discord(username, message, color, timestamp):
    """Send a message to Discord with a timestamp."""
    embed = {
        "title": username,
        "description": message,
        "color": color,
        "timestamp": timestamp.isoformat()
    }
    payload = {"embeds": [embed]}
    
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if response.status_code == 204:
        print(f"Message sent to Discord: {username}: {message}")
    else:
        print(f"Failed to send message: {response.status_code}, {response.text}")

def parse_timestamp(line):
    """Extract and parse the timestamp from a log line, assuming PST."""
    match = re.search(r"<W>(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)", line)
    if match:
        # Parse the log timestamp as PST (no conversion from UTC needed)
        log_time = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S.%f")
        local_time = LOCAL_TIMEZONE.localize(log_time)  # Mark as PST
        return local_time
    return datetime.now(LOCAL_TIMEZONE)  # Fallback to current PST time

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
                    timestamp = parse_timestamp(line)

                    # Match new connections
                    if match := NEW_CONNECTION_PATTERN.search(line):
                        ip = match.group(1)
                        # Ignore these IPs
                        if ip in ("BLOCKEDIP", "BLOCKEDIP2"):
                            print(f"Ignored connection from {ip}")
                            continue
                        send_to_discord("New Connection", f"IP: {ip}", COLOR_JOIN, timestamp)

                    # Match authentications
                    elif match := AUTHENTICATION_PATTERN.search(line):
                        username = match.group(1)
                        send_to_discord(username, "Authenticated", COLOR_CHAT, timestamp)

                    # Match channel changes
                    elif match := CHANNEL_CHANGE_PATTERN.search(line):
                        username, channel = match.groups()
                        color = CHANNEL_COLORS.get(channel, COLOR_CHAT)
                        send_to_discord(username, f"Moved to {channel}", color, timestamp)

                    # Match disconnects
                    elif match := DISCONNECT_PATTERN.search(line):
                        username = match.group(1)
                        send_to_discord(username, "Disconnected", COLOR_DISCONNECT, timestamp)

            last_size = current_size

        time.sleep(1)


if __name__ == "__main__":
    monitor_log(LOG_FILE_PATH)
