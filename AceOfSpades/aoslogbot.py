import time
import re
import requests
from datetime import datetime

# Configuration
DISCORD_WEBHOOK_URL = "yourwebhookurlhere"
LOG_FILE_PATH = r"C:\Users\Administrator\.config\piqueserver\logs\log.txt"  # Adjust if needed

# Regex patterns
JOIN_PATTERN = re.compile(r"\[piqueserver\.player#info\] ([^\s]+) \(IP ([\d\.]+), ID \d+\) entered the game!")
CHAT_PATTERN = re.compile(r"\[piqueserver\.player#info\] <([^>]+)> (.+)")
DISCONNECT_PATTERN = re.compile(r"\[piqueserver\.player#info\] ([^\s]+) disconnected!")

# Send message to Discord
def send_to_discord(message, color=0xCCCCCC):
    payload = {
        "embeds": [{
            "description": message,
            "color": color,
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] {e}")

# Monitor the log file
def monitor_log():
    seen = set()
    while True:
        try:
            with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if line in seen:
                        continue
                    seen.add(line)

                    if match := JOIN_PATTERN.search(line):
                        name, ip = match.groups()
                        send_to_discord(f"**{name}** connected from IP **{ip}**", color=0x00FF00)
                    elif match := CHAT_PATTERN.search(line):
                        name, msg = match.groups()
                        send_to_discord(f"**{name}:** {msg}", color=0xFFFF00)
                    elif match := DISCONNECT_PATTERN.search(line):
                        name = match.group(1)
                        send_to_discord(f"**{name}** disconnected", color=0xFF0000)
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(5)

if __name__ == "__main__":
    monitor_log()
