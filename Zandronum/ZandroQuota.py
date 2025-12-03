#!/usr/bin/env python3
"""
Zandronum Bot Quota Manager (generic/shareable)

Requirements:
- rcon_client.py, huffman.py, headers.py from mega-ice's rcon-zandro repo
- botinfo.txt (vanilla Zandronum bot definitions)
- RCON_PASSWORD set in rcon_client.py

Behavior:
- For each configured server:
    0 humans playing -> 2 bots
    1 human playing  -> 1 bot
    2+ humans        -> 0 bots
- Spectators are ignored (not counted as humans or bots).
- If isTombFetus = True for a server:
    Uses the built-in Tomb Fetus bot names.
- If isTombFetus = False:
    Uses names parsed from botinfo.txt (vanilla bots).
"""

import time
import logging
import re
import requests

from rcon_client import RCONClient, RCON_PASSWORD  # from mega-ice's repo

# ===================== USER CONFIGURATION =====================

# Doomlist API endpoint (leave as-is unless doomlist changes)
doomlistUrl = "https://doomlist.net/api/full"

# Path to vanilla Zandronum botinfo file (for regular servers)
botInfoPath = "botinfo.txt"

# How often to check doomlist and adjust bots (in seconds)
pollIntervalSeconds = 60

# HTTP timeout when talking to doomlist
requestTimeoutSeconds = 5

# Tomb Fetus–specific bot names.
# These will be used only for servers where isTombFetus = True.
tombFetusBotNames = [
    "Burglar",
    "Sociable",
    "Kate",
    "Pat",
    "Pizza",
    "Calibus",
    "Kuckles",
    "Deibu Haburei",
    "Dildy Dong",
    "Doom Sayer",
    "Billerman",
    "Jaret Hujo",
]

# List of servers to manage.
# Edit this section for your setup.
#
# Each entry:
#   ip          - server IP address or hostname
#   port        - Zandronum server port
#   label       - descriptive name for logging
#   isTombFetus - True if this server uses the Tomb Fetus bot names above,
#                 False if it uses regular Zandronum bots from botinfo.txt
servers = [
    {
        "ip": "serveripgoeshere",
        "port": 10665,
        "label": "Tomb Fetus",
        "isTombFetus": True,
    },
    {
        "ip": "serveripgoeshere",
        "port": 10666,
        "label": "Vanilla #1",
        "isTombFetus": False,
    },
    {
        "ip": "serveripgoeshere",
        "port": 10667,
        "label": "Vanilla #2",
        "isTombFetus": False,
    },
    {
        "ip": "serveripgoeshere",
        "port": 10668,
        "label": "Vanilla #3",
        "isTombFetus": False,
    },
]

# ===================== LOGGING SETUP =====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ===================== BOT NAME LOADER =====================

def loadBotNamesFromFile(path: str):
    """
    Parse botinfo.txt and extract all names like:
        name = "Chubbs"
    Returns a sorted list of unique names.
    """
    botNames = set()
    namePattern = re.compile(r'^\s*name\s*=\s*"([^"]+)"')

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                match = namePattern.match(line)
                if match:
                    botNames.add(match.group(1))
    except FileNotFoundError:
        logging.error("Could not find bot info file at %s", path)

    return sorted(botNames)


vanillaBotNames = loadBotNamesFromFile(botInfoPath)
logging.info(
    "Loaded %d vanilla bot names from %s",
    len(vanillaBotNames),
    botInfoPath,
)


# ===================== INTERNAL CONFIG =====================

# Convert servers list into a dict keyed by (ip, port) for convenience
serverConfigs = {}
for cfg in servers:
    key = (cfg["ip"], cfg["port"])
    # Attach the appropriate bot list
    if cfg.get("isTombFetus", False):
        cfg["targetBots"] = tombFetusBotNames
    else:
        cfg["targetBots"] = vanillaBotNames
    serverConfigs[key] = cfg

# One RCON client per server (ip, port)
rconClients = {key: RCONClient() for key in serverConfigs.keys()}


# ===================== DOOMLIST HELPERS =====================

def fetchFullDoomlist():
    """
    Fetch the entire doomlist JSON once per loop.
    """
    response = requests.get(doomlistUrl, timeout=requestTimeoutSeconds)
    response.raise_for_status()
    return response.json()


def getServerInfo(doomlistData, ipAddress: str, port: int):
    """
    Return the entry for ip:port or None if not listed.
    """
    serverKey = f"{ipAddress}:{port}"
    return doomlistData.get(serverKey)


def countHumans(serverInfo):
    """
    Count *playing* humans only:
      - bot == False
      - spec == False
    Ignore spectators.
    """
    if serverInfo is None:
        return 0

    playerData = serverInfo.get("playerdata", [])
    humanCount = 0
    for player in playerData:
        isBot = player.get("bot", False)
        isSpec = player.get("spec", False)
        if (not isBot) and (not isSpec):
            humanCount += 1
    return humanCount


def countBots(serverInfo):
    """
    Count *playing* bots only:
      - bot == True
      - spec == False
    """
    if serverInfo is None:
        return 0

    playerData = serverInfo.get("playerdata", [])
    botCount = 0
    for player in playerData:
        isBot = player.get("bot", False)
        isSpec = player.get("spec", False)
        if isBot and (not isSpec):
            botCount += 1
    return botCount


def getManagedBots(serverInfo, targetNames):
    """
    Return a list of bot names (plain-name) that we are allowed to manage:
      - player.bot == True
      - player.spec == False
      - plain-name exactly matches one of targetNames
    """
    managedBots = []
    if serverInfo is None:
        return managedBots

    playerData = serverInfo.get("playerdata", [])

    for player in playerData:
        if not player.get("bot", False):
            continue

        if player.get("spec", False):
            continue  # ignore spectator bots, if any

        botName = player.get("plain-name") or player.get("name") or ""
        if not botName:
            continue

        if botName in targetNames:
            managedBots.append(botName)

    return managedBots


# ===================== RCON HELPERS =====================

def ensureConnected(ipAddress: str, port: int) -> RCONClient:
    """
    Ensure the RCON client for a given server is connected.
    """
    key = (ipAddress, port)
    client = rconClients[key]
    if not client.running:
        logging.info("Connecting RCON client to %s:%d ...", ipAddress, port)
        client.connect((ipAddress, port), RCON_PASSWORD)
    return client


def sendRconCommand(ipAddress: str, port: int, command: str):
    """
    Ensure connection, then send a single command via RCON for that server.
    """
    client = ensureConnected(ipAddress, port)
    logging.debug("Sending RCON command to %s:%d: %s", ipAddress, port, command)
    client.send_command(command)


# ===================== PER-SERVER LOGIC =====================

def processServer(doomlistData, ipAddress: str, port: int, config: dict):
    label = config.get("label", f"{ipAddress}:{port}")
    targetNames = config["targetBots"]

    serverInfo = getServerInfo(doomlistData, ipAddress, port)

    if not serverInfo:
        logging.warning("[%s:%d] (%s) not found in doomlist (offline or not listed).",
                        ipAddress, port, label)
        return

    humanCount = countHumans(serverInfo)
    botCount = countBots(serverInfo)

    logging.info(
        "[%s:%d] (%s) Humans (playing): %d, Bots (playing): %d",
        ipAddress,
        port,
        label,
        humanCount,
        botCount,
    )

    # Bot quota rules:
    if humanCount <= 0:
        desiredBotCount = 2
    elif humanCount == 1:
        desiredBotCount = 1
    else:
        desiredBotCount = 0

    logging.info(
        "[%s:%d] Desired bots: %d",
        ipAddress,
        port,
        desiredBotCount,
    )

    delta = desiredBotCount - botCount

    if delta > 0:
        # Need more bots: addbot delta times
        logging.info(
            "[%s:%d] Adding %d bot(s).",
            ipAddress,
            port,
            delta,
        )
        for _ in range(delta):
            sendRconCommand(ipAddress, port, "addbot")

    elif delta < 0:
        # Need fewer bots: kick some of our managed bots
        managedBots = getManagedBots(serverInfo, targetNames)
        botsToKickCount = min(-delta, len(managedBots))

        logging.info(
            "[%s:%d] Need to remove %d bot(s). Managed bots present: %s",
            ipAddress,
            port,
            botsToKickCount,
            ", ".join(managedBots) if managedBots else "(none)",
        )

        for botName in managedBots[:botsToKickCount]:
            command = f'kick "{botName}"'
            logging.info(
                "[%s:%d] Kicking bot: %s",
                ipAddress,
                port,
                botName,
            )
            sendRconCommand(ipAddress, port, command)
    else:
        logging.info(
            "[%s:%d] Bot quota already satisfied; no changes.",
            ipAddress,
            port,
        )


# ===================== MAIN LOOP =====================

def main():
    logging.info("Starting Zandronum bot quota manager (generic).")
    logging.info(
        "Managing servers: %s",
        ", ".join(f"{ip}:{port}" for (ip, port) in serverConfigs.keys()),
    )

    try:
        while True:
            try:
                doomlistData = fetchFullDoomlist()
                for (ipAddress, port), cfg in serverConfigs.items():
                    processServer(doomlistData, ipAddress, port, cfg)

            except requests.RequestException as e:
                logging.error("HTTP error talking to doomlist: %s", e)
            except Exception as e:
                logging.exception("Unexpected error: %s", e)

            time.sleep(pollIntervalSeconds)

    except KeyboardInterrupt:
        logging.info("Shutting down quota manager...")
    finally:
        for (ipAddress, port), client in rconClients.items():
            if client.running:
                logging.info(
                    "Disconnecting RCON client for %s:%d",
                    ipAddress,
                    port,
                )
                client.disconnect()


if __name__ == "__main__":
    main()
