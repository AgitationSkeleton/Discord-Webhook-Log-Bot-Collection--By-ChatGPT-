import requests
import time

# Bluesky credentials
USERNAME = "redacted"  # e.g. your@email.com
APP_PASSWORD = "redacted"  # 16-character app password

# Bluesky DID of ghostpolitics
DID = "did:plc:uakd4wsywltz7zeh7cfkrije"

# Discord webhook
DISCORD_WEBHOOK_URL = "redacted"

# Track last seen post
last_seen_uri = None

def create_session():
    url = "https://bsky.social/xrpc/com.atproto.server.createSession"
    response = requests.post(url, json={"identifier": USERNAME, "password": APP_PASSWORD})
    response.raise_for_status()
    return response.json()["accessJwt"]

def fetch_latest_posts(jwt):
    headers = {"Authorization": f"Bearer {jwt}"}
    url = "https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed"
    params = {"actor": DID, "limit": 5}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()["feed"]

def send_to_discord(post):
    content = post["post"]["record"].get("text", "[No text]")
    uri = post["post"]["uri"]
    permalink = f"https://bsky.app/profile/{DID}/post/{uri.split('/')[-1]}"
    message = f" **New Bluesky Post by @ghostreport:**\n{content}\n {permalink}"
    payload = {"content": message}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    response.raise_for_status()

def create_session_with_expiry():
    url = "https://bsky.social/xrpc/com.atproto.server.createSession"
    response = requests.post(url, json={"identifier": USERNAME, "password": APP_PASSWORD})
    response.raise_for_status()
    data = response.json()
    return {
        "jwt": data["accessJwt"],
        "expires_in": 3600 * 4  # 4 hours; adjust if Bluesky gives a real expiry in future
    }


def main():
    global last_seen_uri
    jwt = None
    jwt_expires_at = 0

    while True:
        try:
            # Refresh session only if expired
            if not jwt or time.time() > jwt_expires_at:
                session = create_session_with_expiry()
                jwt = session["jwt"]
                jwt_expires_at = time.time() + session["expires_in"]
                print("[OK] Authenticated to Bluesky.")

            if last_seen_uri is None:
                initial_feed = fetch_latest_posts(jwt)
                if initial_feed:
                    last_seen_uri = initial_feed[0]["post"]["uri"]

            feed = fetch_latest_posts(jwt)
            new_posts = []
            for post in feed:
                uri = post["post"]["uri"]
                if uri == last_seen_uri:
                    break
                new_posts.append(post)
            if new_posts:
                for post in reversed(new_posts):
                    send_to_discord(post)
                    last_seen_uri = post["post"]["uri"]

            time.sleep(30)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print("[!] Rate limited. Backing off for 5 minutes.")
                time.sleep(300)
            else:
                print(f"[!] HTTP error: {e}")
                time.sleep(60)

        except Exception as e:
            print(f"[!] General error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
