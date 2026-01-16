import os
import re
import time
import json
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

import feedparser
import requests
from dateutil import parser as dateparser

try:
    from zoneinfo import ZoneInfo  # py3.9+
except ImportError:
    ZoneInfo = None


# ----------------------------
# Config
# ----------------------------

@dataclass
class FeedSource:
    name: str
    url: str
    min_score_immediate: int = 8
    min_score_digest: int = 5
    max_posts_per_day: int = 1  # per source, per UTC day


FEEDS: List[FeedSource] = [
    FeedSource(
        name="SWLing Post",
        url="https://swling.com/blog/feed/",
        min_score_immediate=8,
        min_score_digest=5,
        max_posts_per_day=1,
    ),
    FeedSource(
        name="r/signalidentification",
        url="https://www.reddit.com/r/signalidentification/.rss",
        min_score_immediate=10,
        min_score_digest=6,
        max_posts_per_day=1,
    ),
    FeedSource(
        name="r/shortwave",
        url="https://www.reddit.com/r/shortwave/.rss",
        min_score_immediate=10,
        min_score_digest=6,
        max_posts_per_day=1,
    ),
]

# Anti-spam limits
GLOBAL_MAX_POSTS_PER_DAY = 3
GLOBAL_MIN_SECONDS_BETWEEN_POSTS = 2 * 60 * 60  # 2 hours
SUPER_HOT_BYPASS_SCORE = 12  # can bypass the 2-hour delay if extremely relevant

# Polling interval
POLL_SECONDS = 15 * 60  # 15 minutes

# Digest schedule (America/Los_Angeles)
DIGEST_TZ = "America/Los_Angeles"
DIGEST_POST_WEEKDAY = 6  # Sunday (Mon=0 ... Sun=6)
DIGEST_POST_HOUR = 10    # 10:00 local
DIGEST_MAX_ITEMS = 5

# Keyword scoring
HIGH_WEIGHT: Dict[str, int] = {
    "numbers station": 6,
    "e06": 6,
    "hm01": 6,
    "v07": 6,
    "uvb-76": 6,
    "the buzzer": 6,
    "atención": 6,
    "lincolnshire poacher": 6,
    "the pip": 6,
    "the squeaky wheel": 6,

    "unidentified signal": 5,
    "mystery signal": 5,
    "odd transmission": 5,
    "strange transmission": 5,
    "interval signal": 5,
    "unknown digital": 5,
}

MED_WEIGHT: Dict[str, int] = {
    "shortwave": 2,
    "hf": 2,
    "pirate radio": 3,
    "pirate": 2,
    "beacon": 2,
    "digital mode": 2,
    "data burst": 2,
    "fsk": 2,
    "psk": 2,
    "rtty": 2,
    "stanag": 3,
    "ale": 2,  # guard with word boundary to reduce false hits
}

NEGATIVE: Dict[str, int] = {
    "for sale": -6,
    "unboxing": -5,
    "review": -3,
    "beginner": -2,
    "how to": -2,
    "guide": -2,
    "ham license": -6,
}

WORD_BOUNDARY_TERMS = {"ale"}


# ----------------------------
# Helpers
# ----------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def utc_day_key() -> str:
    return now_utc().strftime("%Y-%m-%d")

def normalize_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    url = url.split("#", 1)[0]
    if "?" in url:
        base, query = url.split("?", 1)
        parts = []
        for kv in query.split("&"):
            key = kv.split("=", 1)[0].lower()
            if key.startswith("utm_"):
                continue
            parts.append(kv)
        url = base + ("?" + "&".join(parts) if parts else "")
    return url

def stable_id(source_name: str, title: str, url: str) -> str:
    normalized = normalize_url(url)
    raw = f"{source_name}|{(title or '').strip().lower()}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def parse_entry_datetime(entry) -> datetime:
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                dt = dateparser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass

    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return datetime.fromtimestamp(time.mktime(val), tz=timezone.utc)
            except Exception:
                pass

    return now_utc()

def score_text(text: str) -> Tuple[int, List[str]]:
    lower_text = (text or "").lower()
    score = 0
    hits: List[str] = []

    def contains(term: str) -> bool:
        if term in WORD_BOUNDARY_TERMS:
            return re.search(rf"\b{re.escape(term)}\b", lower_text) is not None
        return term in lower_text

    for term, weight in HIGH_WEIGHT.items():
        if contains(term):
            score += weight
            hits.append(term)
    for term, weight in MED_WEIGHT.items():
        if contains(term):
            score += weight
            hits.append(term)
    for term, weight in NEGATIVE.items():
        if contains(term):
            score += weight
            hits.append(term)

    return score, hits

def compact_hits(hits: List[str], max_terms: int = 6) -> str:
    if not hits:
        return ""
    shown = hits[:max_terms]
    suffix = ", ..." if len(hits) > max_terms else ""
    return ", ".join(shown) + suffix

def get_local_now():
    # Prefer correct TZ conversions. If zoneinfo is missing, falls back to local system time.
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(DIGEST_TZ))


# ----------------------------
# SQLite store
# ----------------------------

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS seen_items (
    item_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_utc TEXT NOT NULL,
    score INTEGER NOT NULL,
    queued_digest INTEGER NOT NULL DEFAULT 0,
    posted_immediate INTEGER NOT NULL DEFAULT 0,
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(CREATE_SQL)
        self.conn.commit()

    def get_state(self, key: str, default: str = "") -> str:
        cur = self.conn.execute("SELECT value FROM state WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def seen(self, item_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM seen_items WHERE item_id = ?", (item_id,))
        return cur.fetchone() is not None

    def insert_item(self, item_id: str, source: str, title: str, url: str, published_utc: datetime, score: int,
                    queued_digest: bool, posted_immediate: bool) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_items(item_id, source, title, url, published_utc, score, queued_digest, posted_immediate, created_utc) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item_id,
                source,
                title,
                url,
                published_utc.isoformat(),
                score,
                1 if queued_digest else 0,
                1 if posted_immediate else 0,
                now_utc().isoformat(),
            ),
        )
        self.conn.commit()

    def queue_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(1) FROM seen_items WHERE queued_digest = 1 AND posted_immediate = 0")
        return int(cur.fetchone()[0])

    def fetch_digest_items(self, limit: int) -> List[Tuple[str, str, str, str, str, int]]:
        cur = self.conn.execute(
            "SELECT item_id, source, title, url, published_utc, score "
            "FROM seen_items WHERE queued_digest = 1 AND posted_immediate = 0 "
            "ORDER BY score DESC, published_utc DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def clear_digest_flags(self, item_ids: List[str]) -> None:
        self.conn.executemany("UPDATE seen_items SET queued_digest = 0 WHERE item_id = ?", [(i,) for i in item_ids])
        self.conn.commit()


# ----------------------------
# Webhook posting
# ----------------------------

def post_webhook(webhook_url: str, content: Optional[str] = None, embeds: Optional[List[dict]] = None) -> bool:
    payload: Dict[str, object] = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds

    try:
        resp = requests.post(webhook_url, json=payload, timeout=20)
        if resp.status_code in (200, 204):
            return True
        print(f"[webhook] HTTP {resp.status_code}: {resp.text[:300]}")
        return False
    except Exception as exc:
        print(f"[webhook] error: {exc}")
        return False


def build_embed(source: str, title: str, url: str, published_utc: datetime, score: int, hits: List[str]) -> dict:
    embed = {
        "title": title[:256],
        "url": url,
        "timestamp": published_utc.isoformat(),
        "fields": [
            {"name": "Source", "value": source[:1024], "inline": True},
            {"name": "Score", "value": str(score), "inline": True},
        ],
    }
    why = compact_hits(hits)
    if why:
        embed["fields"].append({"name": "Matched", "value": why[:1024], "inline": False})
    return embed


# ----------------------------
# Rate limiting
# ----------------------------

def can_post_now(store: Store, source_name: str, score: int, per_source_limit: int) -> bool:
    day = utc_day_key()

    global_count = int(store.get_state(f"global_posts_{day}", "0") or "0")
    if global_count >= GLOBAL_MAX_POSTS_PER_DAY:
        return False

    src_count = int(store.get_state(f"src_posts_{source_name}_{day}", "0") or "0")
    if src_count >= per_source_limit:
        return False

    last_post_ts = float(store.get_state("last_post_unix", "0") or "0")
    now_ts = time.time()
    if score < SUPER_HOT_BYPASS_SCORE and (now_ts - last_post_ts) < GLOBAL_MIN_SECONDS_BETWEEN_POSTS:
        return False

    return True


def record_post(store: Store, source_name: str) -> None:
    day = utc_day_key()

    global_count = int(store.get_state(f"global_posts_{day}", "0") or "0")
    src_count = int(store.get_state(f"src_posts_{source_name}_{day}", "0") or "0")

    store.set_state(f"global_posts_{day}", str(global_count + 1))
    store.set_state(f"src_posts_{source_name}_{day}", str(src_count + 1))
    store.set_state("last_post_unix", str(time.time()))


# ----------------------------
# Digest scheduler
# ----------------------------

def should_post_digest(store: Store) -> bool:
    local_now = get_local_now()
    if local_now.weekday() != DIGEST_POST_WEEKDAY:
        return False
    if local_now.hour != DIGEST_POST_HOUR:
        return False

    today_local = local_now.strftime("%Y-%m-%d")
    last_digest = store.get_state("last_digest_date_local", "")
    if last_digest == today_local:
        return False

    return True


def mark_digest_done(store: Store) -> None:
    local_now = get_local_now()
    today_local = local_now.strftime("%Y-%m-%d")
    store.set_state("last_digest_date_local", today_local)


# ----------------------------
# Main loop
# ----------------------------

def poll_once(store: Store, webhook_url: str) -> None:
    for feed in FEEDS:
        try:
            parsed = feedparser.parse(feed.url)
            entries = parsed.entries[:20]
        except Exception as exc:
            print(f"[feed] {feed.name} parse error: {exc}")
            continue

        for entry in entries:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue

            url = normalize_url(link)
            item_id = stable_id(feed.name, title, url)
            if store.seen(item_id):
                continue

            summary = entry.get("summary") or entry.get("description") or ""
            combined = f"{title}\n{summary}"
            score, hits = score_text(combined)
            published_utc = parse_entry_datetime(entry)

            # Decide immediate vs digest queue vs ignore
            if score >= feed.min_score_immediate:
                if can_post_now(store, feed.name, score, feed.max_posts_per_day):
                    embed = build_embed(feed.name, title, url, published_utc, score, hits)
                    ok = post_webhook(webhook_url, embeds=[embed])
                    store.insert_item(
                        item_id, feed.name, title, url, published_utc, score,
                        queued_digest=False, posted_immediate=ok
                    )
                    if ok:
                        record_post(store, feed.name)
                else:
                    # too soon / over cap -> queue if decent
                    queued = score >= feed.min_score_digest
                    store.insert_item(
                        item_id, feed.name, title, url, published_utc, score,
                        queued_digest=queued, posted_immediate=False
                    )

            elif score >= feed.min_score_digest:
                store.insert_item(
                    item_id, feed.name, title, url, published_utc, score,
                    queued_digest=True, posted_immediate=False
                )
            else:
                store.insert_item(
                    item_id, feed.name, title, url, published_utc, score,
                    queued_digest=False, posted_immediate=False
                )


def post_digest_if_due(store: Store, webhook_url: str) -> None:
    if not should_post_digest(store):
        return

    rows = store.fetch_digest_items(DIGEST_MAX_ITEMS)
    mark_digest_done(store)

    if not rows:
        return

    lines = []
    for (_item_id, source, title, url, published_utc, score) in rows:
        lines.append(f"- [{title}]({url}) ({source}, score {score})")

    embed = {
        "title": "Weekly Shortwave / Numbers / Odd Signals Digest",
        "description": "\n".join(lines)[:4096],
        "timestamp": now_utc().isoformat(),
    }

    ok = post_webhook(webhook_url, embeds=[embed])
    if ok:
        store.clear_digest_flags([r[0] for r in rows])


def main() -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise SystemExit("Set DISCORD_WEBHOOK_URL in your environment.")

    db_path = os.getenv("RADIO_FEEDS_DB", "radio_feeds.sqlite3")
    store = Store(db_path)

    if ZoneInfo is None:
        print("[warn] zoneinfo not available (need Python 3.9+). Digest uses host local time instead.")

    print("[ok] Starting feed watcher (webhook mode).")
    print(f"[ok] Digest TZ: {DIGEST_TZ}, weekday={DIGEST_POST_WEEKDAY}, hour={DIGEST_POST_HOUR}")
    print(f"[ok] Polling every {POLL_SECONDS} seconds. Queue currently: {store.queue_count()}")

    while True:
        try:
            poll_once(store, webhook_url)
            post_digest_if_due(store, webhook_url)
        except Exception as exc:
            print(f"[loop] error: {exc}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
