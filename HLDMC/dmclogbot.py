import os
import re
import time
import glob
import requests

# Discord Webhook URL
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL_HERE"  # Replace with your Webhook URL

# Half-Life Goldsrc Log Directory
LOG_DIR = "YOUR_PATH_TO_DMC_HERE\\dmc\\logs"  # Replace with your HLDS log directory

# Regex for parsing events
CHAT_PATTERN = r'L \d+/\d+/\d+ - \d+:\d+:\d+: "(.+)<\d+><STEAM_.+>" say "(.*)"'
JOIN_PATTERN = r'L \d+/\d+/\d+ - \d+:\d+:\d+: "(.+)<\d+><STEAM_.+>" joined team "(.*)"'
LEAVE_PATTERN = r'L \d+/\d+/\d+ - \d+:\d+:\d+: "(.+)<\d+><STEAM_.+>" disconnected'
CONNECT_PATTERN = r'L \d+/\d+/\d+ - \d+:\d+:\d+: "(.+)<\d+><STEAM_.+><>" connected, address "(.*)"'

# Team colors
TEAM_COLORS = {
    "Red": "#FF4C4C",
    "Blue": "#4C4CFF",
    "Green": "#4CFF4C",
    "Yellow": "#FFFF4C",
    "Spectator": "#D3D3D3",
    "": "#FFFFFF"
}

# Store the last processed timestamp to avoid reprocessing lines
last_processed_timestamp = None


def get_most_recent_log():
    """Retrieve the most recent log file in the log directory."""
    log_files = glob.glob(os.path.join(LOG_DIR, '*.log'))
    if log_files:
        return max(log_files, key=os.path.getmtime)
    return None


def delete_old_logs():
    """Delete all log files except the most recent one."""
    most_recent = get_most_recent_log()
    if most_recent:
        for log in glob.glob(os.path.join(LOG_DIR, '*.log')):
            if log != most_recent:
                os.remove(log)


def send_to_discord(content, username="Half-Life Server", color="#808080"):
    """Send a message to Discord via the Webhook."""
    payload = {
        "embeds": [
            {
                "author": {"name": username},
                "description": content,
                "color": int(color.lstrip('#'), 16),
                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())
            }
        ]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code != 204:  # 204 = No Content, Discord's expected response for successful requests
            print(f"Discord Webhook Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error sending to Discord: {e}")


def process_log(log_file):
    """Process the log file for new events."""
    global last_processed_timestamp

    try:
        with open(log_file, 'r', encoding='utf-8') as file:
            lines = file.readlines()
    except Exception as e:
        print(f"Error reading log file: {e}")
        return

    for line in lines:
        # Extract the timestamp to avoid reprocessing
        timestamp_match = re.match(r'L (\d+/\d+/\d+ - \d+:\d+:\d+):', line)
        if timestamp_match:
            timestamp = timestamp_match.group(1)
            if last_processed_timestamp and timestamp <= last_processed_timestamp:
                continue
            last_processed_timestamp = timestamp

        # Match log patterns
        chat_match = re.search(CHAT_PATTERN, line)
        join_match = re.search(JOIN_PATTERN, line)
        leave_match = re.search(LEAVE_PATTERN, line)
        connect_match = re.search(CONNECT_PATTERN, line)

        if chat_match:
            username, message = chat_match.groups()
            send_to_discord(f"**{username}:** {message}", username=username, color=TEAM_COLORS.get("Spectator", "#808080"))
        elif join_match:
            username, team = join_match.groups()
            send_to_discord(f"**{username}** joined team **{team}**", username="Half-Life Server", color=TEAM_COLORS.get(team, "#FFFFFF"))
        elif leave_match:
            username = leave_match.group(1)
            send_to_discord(f"**{username}** left the game.", username="Half-Life Server", color=TEAM_COLORS.get("Red", "#FF4C4C"))
        elif connect_match:
            username, ip_address = connect_match.groups()
            send_to_discord(f"**{username}** connected from IP **{ip_address}**", username="Half-Life Server", color="#32CD32")


if __name__ == "__main__":
    last_processed_timestamp = None
    while True:
        try:
            recent_log = get_most_recent_log()
            if recent_log:
                process_log(recent_log)
            delete_old_logs()
            time.sleep(1)  # Poll every second for changes
        except KeyboardInterrupt:
            print("Stopping bot...")
            break
