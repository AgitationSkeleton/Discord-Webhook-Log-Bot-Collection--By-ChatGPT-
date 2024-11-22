import time
import re
import requests
from datetime import datetime
import pytz
import os

file_path = r"YOUR_ZANDRONUM_LOG_DIRECTORY_HERE"
webhook_url = "YOUR_WEBHOOK_URL_HERE"

# Define PST timezone
pst = pytz.timezone('US/Pacific')

def parse_log_line(line):
    # Get timestamp for messages in PST time zone
    timestamp = datetime.now(pst).isoformat()  # ISO format with correct PST timezone

    # Connection
    if "has connected" in line:
        match = re.search(r"\] (\S+) \(([\d\.]+):\d+\) has connected", line)
        if match:
            return {"type": "connect", "player": match.group(1), "ip": match.group(2), "timestamp": timestamp}

    # Chat
    elif "CHAT" in line:
        match = re.search(r"CHAT (\S+): (.+)", line)
        if match:
            return {"type": "chat", "player": match.group(1), "message": match.group(2), "timestamp": timestamp}

    # Map change
    elif "*** MAP" in line:
        match = re.search(r"\*\*\* MAP\d+: (.+) \*\*\*", line)
        if match:
            return {"type": "map_change", "map": match.group(1), "timestamp": timestamp}

    # Item pickup
    elif "has found" in line:
        match = re.search(r"(\S+) has found the (.+)!", line)
        if match:
            return {"type": "item", "player": match.group(1), "item": match.group(2), "timestamp": timestamp}

    # Exit
    elif "exited the level" in line:
        match = re.search(r"(\S+) exited the level", line)
        if match:
            return {"type": "exit", "player": match.group(1), "timestamp": timestamp}

    # Disconnect
    elif "client" in line and "disconnected" in line:
        match = re.search(r"client (\S+) \(([\d\.]+):\d+\) disconnected", line)
        if match:
            return {"type": "disconnect", "player": match.group(1), "ip": match.group(2), "timestamp": timestamp}

    # Obituaries (Death messages)
    elif "was" in line and ("by a" in line or "by an" in line):
        match = re.search(r"(\S+) was (.+?) by (a|an) (.+)", line)
        if match:
            return {"type": "obituary", "player": match.group(1), "death": match.group(2), "killer": match.group(4), "timestamp": timestamp}

    return None

def post_to_discord(event):
    # Prepare data based on event type
    data = {}

    if event["type"] == "connect":
        data = {"embeds": [{
            "title": "Player Connected",
            "description": f"{event['player']} ({event['ip']})",
            "color": 3066993,
            "timestamp": event["timestamp"]
        }]}

    elif event["type"] == "chat":
        data = {"embeds": [{
            "title": f"{event['player']} says:",
            "description": event["message"],
            "color": 16777215,
            "timestamp": event["timestamp"]
        }]}

    elif event["type"] == "map_change":
        # Check if map initialization to avoid sending map change for the first map load
        if "added to map rotation list" not in event["map"]:
            data = {"embeds": [{
                "title": "Map Changed",
                "description": f"Now playing: {event['map']}",
                "color": 3447003,
                "timestamp": event["timestamp"]
            }]}

    elif event["type"] == "item":
        data = {"embeds": [{
            "title": "Item Found",
            "description": f"{event['player']} found {event['item']}",
            "color": 16776960,
            "timestamp": event["timestamp"]
        }]}

    elif event["type"] == "exit":
        data = {"embeds": [{
            "title": "Player Exited",
            "description": f"{event['player']} exited the level",
            "color": 15158332,
            "timestamp": event["timestamp"]
        }]}

    elif event["type"] == "disconnect":
        data = {"embeds": [{
            "title": "Player Disconnected",
            "description": f"{event['player']} disconnected ({event['ip']})",
            "color": 15158332,
            "timestamp": event["timestamp"]
        }]}

    elif event["type"] == "obituary":
        data = {"embeds": [{
            "title": "Player Death",
            "description": f"{event['player']} was {event['death']} by {event['killer']}",
            "color": 16711680,
            "timestamp": event["timestamp"]
        }]}

    if data:
        requests.post(webhook_url, json=data)

def monitor_log():
    last_modified_time = os.path.getmtime(file_path)  # Track last modified time of the log file
    last_size = os.path.getsize(file_path)  # Track the last size of the file

    with open(file_path, "r") as file:
        # Move to the end of the file
        file.seek(0, 2)
        while True:
            # Get current size and modified time of the log file
            current_size = os.path.getsize(file_path)
            current_modified_time = os.path.getmtime(file_path)

            # Check if the log file was reset (size is drastically reduced or reset)
            if current_size == 0 or current_size < last_size * 0.1:  # Size drastically reduced, maybe reset
                print("Log file has been reset. Restarting monitoring...")
                file.seek(0, 2)  # Reposition to the end of the file if it's reset
                last_modified_time = current_modified_time
                last_size = current_size  # Update size

            elif current_modified_time != last_modified_time:  # In case only timestamp changes
                last_modified_time = current_modified_time
                last_size = current_size  # Update size

            line = file.readline()
            if not line:
                time.sleep(0.1)
                continue
            event = parse_log_line(line.strip())
            if event:
                post_to_discord(event)

if __name__ == "__main__":
    monitor_log()
