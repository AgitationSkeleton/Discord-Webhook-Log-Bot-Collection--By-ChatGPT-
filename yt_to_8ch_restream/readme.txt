🔁 YouTube Restream Bot Setup Guide (Python-based)
This bot monitors a YouTube channel and restreams its live broadcast to a custom RTMP server (e.g., 8chan.tv). It also logs events and errors to a Discord webhook.

✅ Prerequisites
Python 3.9+

FFmpeg installed and either:

Added to PATH, or

Available at C:/ffmpeg/bin/ffmpeg.exe (Windows default fallback)

📦 Required Python Packages
Install with:
pip install aiohttp google-api-python-client yt-dlp

🔧 Configuration
Open the script and set the following values:

YOUTUBE_CHANNEL_ID = "YOUR_CHANNEL_ID_HERE"
YOUTUBE_API_KEY = "YOUR_YOUTUBE_API_KEY_HERE"
RTMP_URL = "rtmp://your-rtmp-server/stream/YOUR_STREAM_KEY"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
YOUTUBE_CHANNEL_ID: Find this from the channel's URL.

YOUTUBE_API_KEY: Create a key via Google Cloud Console (enable the YouTube Data API v3).
RTMP_URL: Your target RTMP stream address and stream key.
DISCORD_WEBHOOK_URL: Your error-reporting Discord webhook.

▶️ Running the Bot
python streamrelay.py
The bot will:

Poll the channel every 15 seconds

Start restreaming if a live video is detected

Stop restreaming once the stream ends

Auto-recover from FFmpeg crashes

Notify your Discord webhook on crashes or failures