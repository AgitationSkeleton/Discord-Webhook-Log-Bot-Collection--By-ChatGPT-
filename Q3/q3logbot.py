import time
import re
import requests
import socket
import subprocess
from pathlib import Path

# Configuration
LOG_FILE_PATH = r"C:\Users\Administrator\AppData\Roaming\Quake3\unlagged\qconsole.log"
DISCORD_WEBHOOK_URL = "YOURWEBHOOKHERE"
IGNORE_LIST_FILE = "ignore_list.txt"

# Embed Colors
COLOR_JOIN = 0x00FF00  # Green
COLOR_DISCONNECT = 0xFF0000  # Red
COLOR_CHAT = 0xFFFFFF  # White

# RCON Configuration
RCON_PASSWORD = "rconpassword"  # <- Replace with your actual RCON password
RCON_ADDRESS = "127.0.0.1"
RCON_PORT = 27960

# Patterns
JOIN_PATTERN = re.compile(r'broadcast: print "(.+?) entered the game\\n"')
CHAT_PATTERN = re.compile(r'say: (.+?): (.+)')
DISCONNECT_PATTERN = re.compile(r'broadcast: print "(.+?) disconnected\\n"')

def load_ignore_list(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            ignore_list = {line.strip() for line in file if line.strip()}
            print(f"Ignoring messages from: {ignore_list}")
            return ignore_list
    except FileNotFoundError:
        print(f"Ignore list file '{file_path}' not found. Proceeding without it.")
        return set()

def sanitize_name(name):
    return re.sub(r"\^\d", "", name)

def send_to_discord(message, color):
    embed = {
        "description": message,
        "color": color
    }
    payload = {"embeds": [embed]}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if response.status_code == 204:
        print(f"Sent: {message}")
    else:
        print(f"Failed to send message: {response.status_code}, {response.text}")

# --- Updated RCON function with proper formatting ---
def send_rcon_command(password, command, address, port):
    try:
        result = subprocess.run(
            ["node", "rcon.js", address, str(port), password, command],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout.strip()
        if output:
            print(f"[RCON RESPONSE] {output}")
        else:
            print("[RCON] No output received.")
    except subprocess.TimeoutExpired:
        print("[RCON ERROR] RCON command timed out.")
    except Exception as e:
        print(f"[RCON ERROR] {e}")

def monitor_log(file_path, ignore_list):
    file_path = Path(file_path)
    last_size = file_path.stat().st_size

    while True:
        current_size = file_path.stat().st_size
        if current_size < last_size:
            print("Log file reset detected.")
            last_size = 0

        if current_size > last_size:
            with file_path.open("r", encoding="utf-8") as file:
                file.seek(last_size)
                for line in file:
                    line = line.strip()

                    # Player join
                    if match := JOIN_PATTERN.search(line):
                        username = sanitize_name(match.group(1))
                        if username not in ignore_list:
                            send_to_discord(f"{username} entered the game", COLOR_JOIN)

                    # Player chat
                    elif match := CHAT_PATTERN.search(line):
                        username, message = map(sanitize_name, match.groups())
                        if username not in ignore_list:
                            send_to_discord(f"{username}: {message}", COLOR_CHAT)

                            # --- Check for !bots command ---
                            bot_match = re.match(r"!bots\s+(\d{1,2})$", message.strip())
                            if bot_match:
                                num = int(bot_match.group(1))
                                if 0 <= num <= 30:
                                    rcon_cmd = f"bot_minplayers {num}"
                                    print(f"[RCON] Setting bot_minplayers to {num}")
                                    send_rcon_command(RCON_PASSWORD, rcon_cmd, RCON_ADDRESS, RCON_PORT)

                    # Player disconnect
                    elif match := DISCONNECT_PATTERN.search(line):
                        username = sanitize_name(match.group(1))
                        if username not in ignore_list:
                            send_to_discord(f"{username} disconnected", COLOR_DISCONNECT)

            last_size = current_size

        time.sleep(1)

if __name__ == "__main__":
    ignore_list = load_ignore_list(IGNORE_LIST_FILE)
    monitor_log(LOG_FILE_PATH, ignore_list)
