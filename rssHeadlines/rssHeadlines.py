import feedparser
import requests
import schedule
import time
from datetime import datetime
import pytz

# Your Discord webhook URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/your_webhook_here"

# RSS feed sources
rss_feeds = {
    "Tom's Hardware": "https://www.tomshardware.com/feeds/all",
    "AnandTech": "https://www.anandtech.com/rss",
    "TechPowerUp": "https://www.techpowerup.com/rss/news.xml",
    "VideoCardz": "https://videocardz.com/feed",
    "WCCFTech": "https://wccftech.com/feed/"
}

# Gather headlines from all feeds
def collect_headlines(max_per_source=3):
    headlines = []
    for source, url in rss_feeds.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_per_source]:
            title = entry.title
            link = entry.link
            # Make link suppress embeds with angle brackets inside markdown
            formatted_link = f"[{title}](<{link}>)"
            headlines.append(f"**{source}**: {formatted_link}")
    return headlines

# Send headlines to Discord
def send_to_discord(headlines):
    pst = pytz.timezone("US/Pacific")
    now_pst = datetime.now(pst).strftime("%Y-%m-%d %I:%M %p %Z")

    content = "\n".join(headlines)
    payload = {
        "content": f"**📰 Daily Hardware Headlines (CPUs/GPUs)** — *{now_pst}*\n\n{content}"
    }

    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    print(f"[{datetime.now()}] Sent {len(headlines)} headlines: {response.status_code}")

# Job to run daily at noon PST
def daily_task():
    headlines = collect_headlines()
    send_to_discord(headlines)

# Schedule the task
schedule.every().day.at("12:00").do(daily_task)

print("RSS to Discord bot running. Waiting for scheduled job...")

while True:
    schedule.run_pending()
    time.sleep(30)
