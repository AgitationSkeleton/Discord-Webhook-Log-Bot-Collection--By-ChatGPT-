import discord
import asyncio
import os
import shutil
import requests
from datetime import time, timezone
from discord.ext import tasks, commands

TOKEN = "YOUR_BOT_TOKEN_HERE"
CHANNEL_IDS = [CHANNEL1, CHANNEL2]
BACKUP_DIR = "C:\\PATH_TO_UR_WORLD_FOLDER"
ARCHIVE_PATH = "C:\\PATH_TO_UR_SERVER_FOLDER\\yourworldnamehere.xz"
CATBOX_URL = "https://catbox.moe/user/api.php"
OWNER_ID = YOUR_DISCORD_ID_HERE

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="~", intents=intents)

async def send_error_message(error_message):
    """Sends an error message to the designated Discord channels."""
    for channel_id in CHANNEL_IDS:
        channel = client.get_channel(channel_id)
        if channel:
            await channel.send(f"❌ Backup Error: {error_message}")

def upload_to_catbox(file_path):
    """Uploads a file to Catbox.moe and returns the file URL."""
    with open(file_path, 'rb') as file:
        response = requests.post(
            CATBOX_URL,
            files={'fileToUpload': file},
            data={'reqtype': 'fileupload'}
        )
        
        if response.status_code == 200 and response.text.startswith("https"):
            return response.text.strip()
        return None

async def perform_backup():
    """Handles the backup process, uploads it to Catbox, and posts the link."""
    try:
        # Create tar.xz archive
        shutil.make_archive(ARCHIVE_PATH[:-7], 'xztar', BACKUP_DIR)

        if not os.path.exists(ARCHIVE_PATH):
            await send_error_message("Archive creation failed.")
            return

        # Upload to Catbox.moe
        file_url = upload_to_catbox(ARCHIVE_PATH)
        if not file_url:
            await send_error_message("Failed to upload backup to Catbox.moe.")
            return

        # Send link to Discord channels
        for channel_id in CHANNEL_IDS:
            channel = client.get_channel(channel_id)
            if channel:
                await channel.send(f"Daily redchanit_retroworld backup: {file_url}")
            else:
                await send_error_message(f"Channel {channel_id} not found.")
                return

        # Delete the archive after successful upload
        os.remove(ARCHIVE_PATH)
        print("Backup successfully uploaded to Catbox.moe and deleted.")
    except Exception as e:
        await send_error_message(f"Error during backup process: {e}")

@tasks.loop(time=time(11, 1, tzinfo=timezone.utc))  # 3:01 AM PST
async def scheduled_backup():
    await perform_backup()

@client.command()
async def btabackup(ctx):
    """Manually triggers the backup, only for the owner."""
    if ctx.author.id == OWNER_ID:
        await ctx.send("Forcing backup and upload...")
        await perform_backup()
    else:
        await ctx.send("You do not have permission to run this command.")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    scheduled_backup.start()

client.run(TOKEN)
