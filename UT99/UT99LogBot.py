import re
import time
from datetime import datetime
import requests
import pytz

# Configuration
log_file_path = r"YOUR_PATH_TO_UT99\Unreal\UnrealTournament\System\server.log"
webhook_url = "YOUR_WEBHOOK_URL_HERE"

# Discord Embed Colors
COLORS = {
    "join": 0x00FF00,  # Green
    "map_change": 0xFFFF00,  # Yellow
}

# Regex patterns for log parsing
PATTERNS = {
    "join": re.compile(r"DevNet: Join succeeded: (.+)"),
    "map_change": re.compile(r"ScriptLog: ProcessServerTravel: (.+\.unr)"),
}

def send_discord_message(event_type, description, timestamp):
    """
    Sends a message to the Discord webhook.
    """
    embed = {
        "title": f"Server Event: {event_type.capitalize()}",
        "description": description,
        "color": COLORS.get(event_type, 0xFFFFFF),  # Default to white
        "timestamp": timestamp.isoformat(),
    }
    response = requests.post(webhook_url, json={"embeds": [embed]})
    if response.status_code != 204:
        print(f"Failed to send Discord message: {response.status_code}, {response.text}")

def tail_log(file_path):
    """
    Tails the log file and yields new lines as they're added.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        f.seek(0, 2)  # Move to the end of the file
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line.strip()

def parse_log_line(line):
    """
    Parses a single log line for relevant events.
    """
    for event_type, pattern in PATTERNS.items():
        match = pattern.search(line)
        if match:
            if event_type == "join":
                return event_type, f"Player joined: {match.group(1)}"
            if event_type == "map_change":
                return event_type, f"Map changed to: {match.group(1)}"
    return None, None

def main():
    """
    Main function to monitor the log and send Discord messages.
    """
    print("Monitoring UT99 server log...")
    
    # Set timezone to PST (Pacific Standard Time)
    pst = pytz.timezone('US/Pacific')

    for line in tail_log(log_file_path):
        event_type, description = parse_log_line(line)
        if event_type:
            # Get current local time and convert to PST
            timestamp = datetime.now(pst)  # Convert to PST timezone
            print(f"[{timestamp}] {event_type.upper()}: {description}")
            send_discord_message(event_type, description, timestamp)

if __name__ == "__main__":
    main()
