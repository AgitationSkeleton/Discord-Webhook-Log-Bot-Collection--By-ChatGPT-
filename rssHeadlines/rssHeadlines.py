import feedparser
import requests
import schedule
import time
from datetime import datetime
import pytz
import html

DISCORD_WEBHOOK_URL = "insertwebhook"

rss_feeds = {
    "Tom's Hardware": "https://www.tomshardware.com/feeds/all",
    "AnandTech": "https://www.anandtech.com/rss",
    "TechPowerUp": "https://www.techpowerup.com/rss/news.xml",
    "VideoCardz": "https://videocardz.com/feed",
    "WCCFTech": "https://wccftech.com/feed/"
}

vegas_deal_feed = "https://www.reddit.com/r/Gamebundles/.rss"
vegas_keywords = ["sony vegas", "vegas pro", "magix vegas"]

def collect_headlines(max_per_source=3):
    headlines = []
    for source, url in rss_feeds.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:max_per_source]:
            title = html.unescape(entry.title).replace("]", "\\]").replace("[", "\\[").replace(")", "\\)").replace("(", "\\(")
            link = entry.link
            formatted_link = f"[{title}](<{link}>)"
            headlines.append(f"**{source}**: {formatted_link}")
    return headlines

def collect_vegas_deals():
    feed = feedparser.parse(vegas_deal_feed)
    matches = []
    for entry in feed.entries:
        content = f"{entry.title} {entry.get('summary', '')}".lower()
        if any(keyword in content for keyword in vegas_keywords):
            title = html.unescape(entry.title).replace("]", "\\]").replace("[", "\\[").replace(")", "\\)").replace("(", "\\(")
            link = entry.link
            formatted_link = f"[{title}](<{link}>)"
            matches.append(f"**Vegas Deal**: {formatted_link}")
    return matches

def send_to_discord(headlines, label_as_daily=True):
    pst = pytz.timezone("US/Pacific")
    now_pst = datetime.now(pst).strftime("%Y-%m-%d %I:%M %p %Z")

    vegas_deals = collect_vegas_deals()
    label = "**📰 Daily Hardware Headlines (CPUs/GPUs)** — *" + now_pst + "*\n\n" if label_as_daily else "**📰 Hardware Headlines Preview**\n\n"

    max_length = 1900
    full_message = label
    total_length = len(full_message)
    safe_headlines = []

    for line in headlines:
        projected = total_length + len(line) + 1
        if projected >= max_length:
            break
        safe_headlines.append(line)
        total_length = projected

    full_message += "\n".join(safe_headlines)

    payload = {"content": full_message}
    print(f"[{datetime.now()}] Payload length: {len(full_message)} characters")
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    print(f"[{datetime.now()}] Sent {len(safe_headlines)} headlines (+ {len(vegas_deals)} vegas): {response.status_code}")
    if response.status_code != 204:
        print("Discord response:", response.text)

    # If Vegas deals exist and didn't fit, send them separately
    if vegas_deals:
        vegas_block = "**🎬 Sony Vegas Deals Found:**\n" + "\n".join(vegas_deals)
        if total_length + len(vegas_block) >= 2000:
            vegas_payload = {"content": vegas_block}
            vegas_response = requests.post(DISCORD_WEBHOOK_URL, json=vegas_payload)
            print(f"[{datetime.now()}] Sent Vegas deals as separate message: {vegas_response.status_code}")
            if vegas_response.status_code != 204:
                print("Discord response:", vegas_response.text)

def daily_task():
    headlines = collect_headlines()
    send_to_discord(headlines, label_as_daily=True)

schedule.every().day.at("12:00").do(daily_task)

print("Performing test headline post...")
test_headlines = collect_headlines()
send_to_discord(test_headlines, label_as_daily=False)

print("RSS to Discord bot running. Waiting for scheduled job...")

while True:
    schedule.run_pending()
    time.sleep(30)
