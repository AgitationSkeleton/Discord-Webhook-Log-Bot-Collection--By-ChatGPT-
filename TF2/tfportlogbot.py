import os
import re
import time
import glob
import requests

# Discord Webhook URL
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_URL_HERE"

# Source Engine Log Directory
LOG_DIR = "YOUR_PATH_TO_TF_FOLDER_HERE\\logs"

# Regex patterns for log parsing
CONNECT_PATTERN = r'L (\d+/\d+/\d+ - \d+:\d+:\d+): "([^<]+)<\d+><(\[U:\d:\d+\])><>" connected, address "([^"]+)"'
VALIDATED_PATTERN = r'L (\d+/\d+/\d+ - \d+:\d+:\d+): "([^<]+)<\d+><(\[U:\d:\d+\])><>" STEAM USERID validated'
ENTER_GAME_PATTERN = r'L (\d+/\d+/\d+ - \d+:\d+:\d+): "([^<]+)<\d+><(\[U:\d:\d+\])><>" entered the game'
TEAM_JOIN_PATTERN = r'L (\d+/\d+/\d+ - \d+:\d+:\d+): "([^<]+)<\d+><(\[U:\d:\d+\])><(Unassigned|Blue|Red|Spectator)>" joined team "([^"]+)"'
CHAT_PATTERN = r'L (\d+/\d+/\d+ - \d+:\d+:\d+): "([^<]+)<\d+><(\[U:\d:\d+\])><([^>]+)>" say "(.*)"'
DISCONNECT_PATTERN = r'L (\d+/\d+/\d+ - \d+:\d+:\d+): "([^<]+)<\d+><(\[U:\d:\d+\])><([^>]+)>" disconnected.*'

# Team colors
TEAM_COLORS = {
    "Unassigned": 0x000000,
    "Blue": 0x0000FF,
    "Red": 0xFF0000,
    "Spectator": 0xAAAAAA,
}

def send_discord_message(title, description, color=0x7289DA):
    """Send a message to Discord via webhook."""
    data = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
            }
        ]
    }
    response = requests.post(DISCORD_WEBHOOK_URL, json=data)
    if response.status_code != 204:
        print(f"Failed to send message to Discord: {response.status_code}, {response.text}")

def process_log_line(line):
    """Process a single log line and send appropriate Discord messages."""
    if match := re.match(CONNECT_PATTERN, line):
        timestamp, player, steam_id, address = match.groups()
        send_discord_message(
            "Player Connected",
            f"**[{timestamp}]** **{player}** (`{steam_id}`) connected from `{address}`.",
            0x00FF00  # Explicitly set to green (0x00FF00)
        )
    elif match := re.match(VALIDATED_PATTERN, line):
        timestamp, player, steam_id = match.groups()
        send_discord_message(
            "Player Validated",
            f"**[{timestamp}]** **{player}** (`{steam_id}`) has been validated.",
            TEAM_COLORS["Unassigned"]
        )
    elif match := re.match(ENTER_GAME_PATTERN, line):
        timestamp, player, steam_id = match.groups()
        send_discord_message(
            "Player Entered the Game",
            f"**[{timestamp}]** **{player}** (`{steam_id}`) has entered the game.",
            TEAM_COLORS["Unassigned"]
        )
    elif match := re.match(TEAM_JOIN_PATTERN, line):
        timestamp, player, steam_id, old_team, new_team = match.groups()
        send_discord_message(
            "Team Change",
            f"**[{timestamp}]** **{player}** (`{steam_id}`) joined team **{new_team}**.",
            TEAM_COLORS.get(new_team, 0x7289DA)
        )
    elif match := re.match(CHAT_PATTERN, line):
        timestamp, player, steam_id, team, message = match.groups()
        send_discord_message(
            f"Chat - {team} Team",
            f"**[{timestamp}]** **{player}** (`{steam_id}`): {message}",
            TEAM_COLORS.get(team, 0x7289DA)
        )
    elif match := re.match(DISCONNECT_PATTERN, line):
        timestamp, player, steam_id, team = match.groups()
        send_discord_message(
            "Player Disconnected",
            f"**[{timestamp}]** **{player}** (`{steam_id}`) has disconnected.",
            0xFF0000
        )

def monitor_logs():
    """Monitor log files for new entries."""
    log_files = glob.glob(os.path.join(LOG_DIR, "*.log"))
    log_files.sort(key=os.path.getmtime, reverse=True)  # Process the latest log file first

    if not log_files:
        print("No log files found.")
        return

    latest_log = log_files[0]
    print(f"Monitoring log file: {latest_log}")

    with open(latest_log, "r", encoding="utf-8") as log_file:
        log_file.seek(0, os.SEEK_END)  # Start at the end of the file
        while True:
            line = log_file.readline()
            if line:
                process_log_line(line.strip())
            else:
                time.sleep(0.1)

if __name__ == "__main__":
    monitor_logs()
