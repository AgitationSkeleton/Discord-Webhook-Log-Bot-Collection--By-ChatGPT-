import requests
import time
import threading
import os

# Configuration
USERNAME = "your@email.com"
APP_PASSWORD = "your_app_password"
ACCOUNTS_FILE = "accounts.txt"
POLL_INTERVAL = 30  # seconds
SEEN_DIR = "seen"

# Ensure the 'seen' directory exists
os.makedirs(SEEN_DIR, exist_ok=True)

# Cache for DID-to-handle mapping
handle_cache = {}

def resolve_did_to_handle(did):
    if did in handle_cache:
        return handle_cache[did]
    url = f"https://bsky.social/xrpc/com.atproto.identity.resolveDid?did={did}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        handle = response.json().get("handle", did)
        handle_cache[did] = handle
        return handle
    except Exception as e:
        print(f"[!] Failed to resolve DID {did}: {e}")
        return did

def create_session_with_expiry():
    url = "https://bsky.social/xrpc/com.atproto.server.createSession"
    response = requests.post(url, json={"identifier": USERNAME, "password": APP_PASSWORD})
    response.raise_for_status()
    data = response.json()
    return {
        "jwt": data["accessJwt"],
        "expires_in": 3600 * 4  # Estimated expiry: 4 hours
    }

def fetch_latest_posts(jwt, did):
    headers = {"Authorization": f"Bearer {jwt}"}
    url = "https://bsky.social/xrpc/app.bsky.feed.getAuthorFeed"
    params = {"actor": did, "limit": 5}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()["feed"]

def send_to_discord(post, webhook_url, did):
    content = post["post"]["record"].get("text", "[No text]")
    uri = post["post"]["uri"]
    permalink = f"https://bsky.app/profile/{did}/post/{uri.split('/')[-1]}"
    handle = resolve_did_to_handle(did)
    message = f"**New Bluesky Post by @{handle}:**\n{content}\n🔗 {permalink}"
    payload = {"content": message}
    response = requests.post(webhook_url, json=payload)
    response.raise_for_status()

def monitor_account(jwt, did, webhook):
    print(f"[+] Monitoring {did}")
    seen_file = os.path.join(SEEN_DIR, f"{did.replace(':', '_')}.txt")
    last_seen_uri = None

    # Load last seen URI from file if available
    if os.path.exists(seen_file):
        with open(seen_file, "r", encoding="utf-8") as f:
            last_seen_uri = f.read().strip()
    else:
        # Warm-up: Set last_seen_uri without posting
        try:
            feed = fetch_latest_posts(jwt, did)
            if feed:
                last_seen_uri = feed[0]["post"]["uri"]
                with open(seen_file, "w", encoding="utf-8") as f:
                    f.write(last_seen_uri)
        except Exception as e:
            print(f"[{did}] Error during warm-up: {e}")

    while True:
        try:
            feed = fetch_latest_posts(jwt, did)
            new_posts = []
            for post in feed:
                uri = post["post"]["uri"]
                if uri == last_seen_uri:
                    break
                new_posts.append(post)

            if new_posts:
                for post in reversed(new_posts):
                    send_to_discord(post, webhook, did)
                    last_seen_uri = post["post"]["uri"]
                    with open(seen_file, "w", encoding="utf-8") as f:
                        f.write(last_seen_uri)

            time.sleep(POLL_INTERVAL)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                print(f"[!] {did} rate limited. Sleeping 5 minutes.")
                time.sleep(300)
            else:
                print(f"[!] HTTP error for {did}: {e}")
                time.sleep(60)
        except Exception as e:
            print(f"[!] General error for {did}: {e}")
            time.sleep(60)

def load_accounts():
    accounts = {}
    current_did = None
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_did = line[1:-1]
            elif line.startswith("webhook=") and current_did:
                accounts[current_did] = line.split("=", 1)[1]
    return accounts

def main():
    print("[*] Starting Bluesky relay bot...")
    session = create_session_with_expiry()
    jwt = session["jwt"]
    jwt_expires_at = time.time() + session["expires_in"]

    accounts = load_accounts()
    for did, webhook in accounts.items():
        thread = threading.Thread(target=monitor_account, args=(jwt, did, webhook), daemon=True)
        thread.start()

    while True:
        if time.time() > jwt_expires_at:
            session = create_session_with_expiry()
            jwt = session["jwt"]
            jwt_expires_at = time.time() + session["expires_in"]
            print("[*] Session refreshed.")
        time.sleep(60)

if __name__ == "__main__":
    main()
