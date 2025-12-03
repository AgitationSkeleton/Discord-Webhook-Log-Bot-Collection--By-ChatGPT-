import time
import re
import requests
from datetime import datetime, timedelta
import pytz
import os

log_dir = r"E:\path_to_\tombfetus"
webhook_url = "webhook"

pst = pytz.timezone('US/Pacific')

def get_latest_log_file():
    log_files = [f for f in os.listdir(log_dir) if f.lower().endswith('.log')]
    if not log_files:
        return None
    log_files.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)), reverse=True)
    return os.path.join(log_dir, log_files[0])

def parse_log_line(line):
    timestamp = datetime.now(pst).isoformat()

    # Ignore system/noise lines
    if (
        "Connect (v3.2)" in line
        or "compatflags changed to" in line
        or "compatflags2 changed to" in line
    ):
        return None

    # Ignore any Final Velocity status lines outright
    if "Final Velocity" in line:
        # If you ONLY want to ignore chat and not e.g. joins, tighten this:
        # if "Final Velocity says" in line:
        return None

    if "has connected" in line:
        match = re.search(r"\] (\S+) \(([\d\.]+):\d+\) has connected", line)
        if match:
            return {
                "type": "connect",
                "player": match.group(1),
                "ip": match.group(2),
                "timestamp": timestamp
            }

    # Player chat using "NAME: message" format
    elif re.search(r"]\s.*?:\s", line):
        match = re.search(r"]\s(.*?):\s(.+)", line)
        if match:
            player_name = match.group(1).strip()
            message_text = match.group(2).strip()

            # Ignore messages where the "player" is Final Velocity
            if player_name.lower().startswith("final velocity"):
                return None

            if player_name.lower().startswith("sendnetworkstring"):
                return None

            if player_name.lower().startswith("unknown player"):
                return None

            return {
                "type": "chat",
                "player": player_name,
                "message": message_text,
                "timestamp": timestamp
            }

    elif "*** MAP" in line:
        match = re.search(r"\*\*\* MAP\d+: (.+) \*\*\*", line)
        if match:
            return {"type": "map_change", "map": match.group(1), "timestamp": timestamp}

    elif "*** LIME" in line:
        match = re.search(r"\*\*\* LIME\d+: (.+) \*\*\*", line)
        if match:
            return {"type": "map_change", "map": match.group(1), "timestamp": timestamp}

    elif "has found" in line:
        match = re.search(r"(\S+) has found the (.+)!", line)
        if match:
            return {
                "type": "item",
                "player": match.group(1),
                "item": match.group(2),
                "timestamp": timestamp
            }

    elif "exited the level" in line:
        match = re.search(r"(\S+) exited the level", line)
        if match:
            return {"type": "exit", "player": match.group(1), "timestamp": timestamp}

    elif "client" in line and "disconnected" in line:
        match = re.search(r"client (\S+) \(([\d\.]+):\d+\) disconnected", line)
        if match:
            return {
                "type": "disconnect",
                "player": match.group(1),
                "ip": match.group(2),
                "timestamp": timestamp
            }

    elif "was" in line and ("by a" in line or "by an" in line):
        match = re.search(r"(\S+) was (.+?) by (a|an) (.+)", line)
        if match:
            return {
                "type": "obituary",
                "player": match.group(1),
                "death": match.group(2),
                "killer": match.group(4),
                "timestamp": timestamp
            }

    return None

def post_to_discord(event):
    embed = {
        "timestamp": event["timestamp"]
    }

    if event["type"] == "connect":
        embed.update({
            "title": "Player Connected",
            "description": f"{event['player']} ({event['ip']})",
            "color": 3066993
        })
    elif event["type"] == "chat":
        embed.update({
            "title": f"{event['player']} says:",
            "description": event["message"],
            "color": 16777215
        })
    elif event["type"] == "map_change":
        if "added to map rotation list" not in event["map"]:
            embed.update({
                "title": "Map Changed",
                "description": f"Now playing: {event['map']}",
                "color": 3447003
            })
    elif event["type"] == "item":
        embed.update({
            "title": "Item Found",
            "description": f"{event['player']} found {event['item']}",
            "color": 16776960
        })
    elif event["type"] == "exit":
        embed.update({
            "title": "Player Exited",
            "description": f"{event['player']} exited the level",
            "color": 15158332
        })
    elif event["type"] == "disconnect":
        embed.update({
            "title": "Player Disconnected",
            "description": f"{event['player']} disconnected ({event['ip']})",
            "color": 15158332
        })
    elif event["type"] == "obituary":
        embed.update({
            "title": "Player Death",
            "description": f"{event['player']} was {event['death']} by {event['killer']}",
            "color": 16711680
        })

    if "title" in embed:
        requests.post(webhook_url, json={"embeds": [embed]})

def monitor_log():
    current_file = get_latest_log_file()
    if not current_file:
        print("No .log files found in directory.")
        return

    print(f"Monitoring: {current_file}")
    last_check_time = time.time()

    with open(current_file, "r", encoding="utf-8", errors="ignore") as file:
        file.seek(0, 2)
        while True:
            now = datetime.now(pst)
            if now.hour == 3 and now.minute == 0:
                print("3AM reached. Restarting application...")
                os.execv(__file__, [__file__])

            # Check every 5 minutes for a newer file
            if time.time() - last_check_time > 300:
                new_file = get_latest_log_file()
                if new_file != current_file:
                    print(f"Switching to new file: {new_file}")
                    current_file = new_file
                    file.close()
                    file = open(current_file, "r", encoding="utf-8", errors="ignore")
                    file.seek(0, 2)
                last_check_time = time.time()

            line = file.readline()
            if not line:
                time.sleep(0.1)
                continue

            event = parse_log_line(line.strip())
            if event:
                post_to_discord(event)

if __name__ == "__main__":
    monitor_log()
