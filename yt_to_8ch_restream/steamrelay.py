import asyncio
import subprocess
import logging
import shutil
import aiohttp
import time
import requests
from googleapiclient.discovery import build
import yt_dlp
import googleapiclient.discovery

# Disable googleapiclient caching warning
import googleapiclient._helpers
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='googleapiclient')
googleapiclient._helpers.positional_parameters_enforcement = None

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# YouTube and RTMP config
YOUTUBE_CHANNEL_ID = "UCpmFso2r78-omUEXDzxsX2g"  # ghostpolitics
YOUTUBE_API_KEY = "YOUR_YOUTUBE_API_KEY_HERE"  # Replace with your API key
RTMP_URL = "rtmp://8chan.tv/stream/YOUR_KEY_HERE"
DISCORD_WEBHOOK_URL = "YOUR_DISCORD_WEBHOOK_HERE"

FFMPEG_PATH = shutil.which("ffmpeg") or "C:/ffmpeg/bin/ffmpeg.exe"
STREAM_POLL_INTERVAL = 15
MAX_RESTARTS = 5
ffmpeg_proc = None
restart_attempts = 0

async def report_error_to_discord(message):
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(DISCORD_WEBHOOK_URL, json={"content": message})
        except Exception as e:
            logging.warning(f"Failed to send error to Discord: {e}")

def get_live_video_id():
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        request = youtube.search().list(
            part="snippet",
            channelId=YOUTUBE_CHANNEL_ID,
            eventType="live",
            type="video"
        )
        response = request.execute()
        items = response.get("items", [])
        if items:
            return items[0]["id"]["videoId"]
    except Exception as e:
        logging.warning(f"Failed to fetch live stream from YouTube API: {e}")
    return None

def get_stream_url(video_id):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best[ext=mp4]/best',
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return info.get("url")
    except Exception as e:
        logging.error(f"yt-dlp failed: {e}")
    return None

async def log_ffmpeg_output():
    global ffmpeg_proc, restart_attempts
    if not ffmpeg_proc:
        return

    while True:
        line = ffmpeg_proc.stdout.readline()
        if line:
            logging.info(f"[FFmpeg] {line.strip()}")
        if ffmpeg_proc.poll() is not None:
            logging.warning("FFmpeg process exited unexpectedly.")
            await report_error_to_discord("FFmpeg crashed. Attempting to restart.")
            restart_attempts += 1
            if restart_attempts > MAX_RESTARTS:
                logging.error("Too many FFmpeg restarts. Giving up.")
                await report_error_to_discord("FFmpeg crashed too many times. Giving up.")
                return
            await asyncio.sleep(min(10 * restart_attempts, 60))
            await try_start_ffmpeg()
            break
        await asyncio.sleep(0.5)

async def try_start_ffmpeg():
    global ffmpeg_proc, restart_attempts

    video_id = get_live_video_id()
    if not video_id:
        logging.info("No active live stream found.")
        return

    stream_url = get_stream_url(video_id)
    if not stream_url:
        await report_error_to_discord("Live stream detected but failed to extract stream URL.")
        return

    logging.info("Starting FFmpeg restream...")
    try:
        ffmpeg_proc = subprocess.Popen([
            FFMPEG_PATH, "-re", "-i", stream_url,
            "-c:v", "copy", "-c:a", "aac",
            "-f", "flv",
            "-g", "30", "-b:v", "3500k",
            RTMP_URL
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        asyncio.create_task(log_ffmpeg_output())
        restart_attempts = 0
        logging.info("FFmpeg process started.")
    except Exception as e:
        logging.error(f"Failed to start FFmpeg: {e}")
        await report_error_to_discord(f"Failed to start FFmpeg: {e}")

async def monitor_youtube():
    global ffmpeg_proc
    last_live = False
    while True:
        video_id = get_live_video_id()
        is_live = video_id is not None

        if is_live and not last_live:
            logging.info("Ghost is now live on YouTube. Starting restream...")
            await try_start_ffmpeg()
            last_live = True

        elif not is_live and last_live:
            logging.info("Ghost is now offline. Stopping restream...")
            stop_ffmpeg()
            last_live = False

        await asyncio.sleep(STREAM_POLL_INTERVAL)

def stop_ffmpeg():
    global ffmpeg_proc
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        logging.info("Stopping FFmpeg restream...")
        ffmpeg_proc.terminate()
        ffmpeg_proc.wait()
        logging.info("FFmpeg process terminated.")
    ffmpeg_proc = None

if __name__ == "__main__":
    try:
        logging.info("Starting YouTube restream bot...")
        asyncio.run(monitor_youtube())
    except KeyboardInterrupt:
        stop_ffmpeg()
        logging.info("Bot stopped by user.")
