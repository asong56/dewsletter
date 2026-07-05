from datetime import datetime, timedelta, UTC
from pathlib import Path
import xml.etree.ElementTree as ET
import os

import requests
import feedparser
import trafilatura

from db_write import insert_item, insert_error, item_exists
from hash import generate_item_id


OPML_PATH    = Path("feed.opml")
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "8"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def retry_filter() -> str | None:
    return os.getenv("RETRY_ONLY_SOURCE")


# ── OPML parsing ─────────────────────────────────────────────────────────────

def load_feeds() -> list[tuple[str, str]]:
    """
    Parse feed.opml and return (feed_url, category) pairs.
    Flat feeds (not inside a folder outline) get category = ''.
    """
    tree = ET.parse(OPML_PATH)
    feeds: list[tuple[str, str]] = []

    def walk(node: ET.Element, category: str = "") -> None:
        for child in node:
            if child.tag != "outline":
                continue
            url = child.attrib.get("xmlUrl", "")
            if url:
                feeds.append((url, category))
            else:
                # Folder outline — its text attribute becomes the category name
                walk(child, child.attrib.get("text", ""))

    body = tree.getroot().find("body")
    if body is not None:
        walk(body)

    return feeds


# ── Content extraction ────────────────────────────────────────────────────────

def extract(url: str) -> str | None:
    """
    Fetch and extract article text as Markdown.
    Falls back to archive.org if the primary request yields nothing.
    """
    # Primary
    raw = trafilatura.fetch_url(url)
    if raw:
        text = trafilatura.extract(raw, output_format="markdown")
        if text:
            return text

    # Fallback: Wayback Machine (archive.org is reachable from GH Actions)
    try:
        wayback = f"https://web.archive.org/web/{url}"
        raw = trafilatura.fetch_url(wayback, config=_fast_config())
        if raw:
            return trafilatura.extract(raw, output_format="markdown")
    except Exception:
        pass

    return None


def _fast_config():
    """Short timeout for archive.org fallback so it never blocks ingest."""
    cfg = trafilatura.settings.use_config()
    cfg.set("DEFAULT", "DOWNLOAD_TIMEOUT", "10")
    return cfg


# ── Date filtering ────────────────────────────────────────────────────────────

def is_recent(entry) -> bool:
    """
    Return False only when the entry has a parseable date older than LOOKBACK_DAYS.
    Missing or unparseable dates are treated as recent (fail-open).
    """
    published = entry.get("published_parsed")
    if published is None:
        return True
    try:
        pub_dt  = datetime(*published[:6], tzinfo=UTC)
        cutoff  = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
        return pub_dt >= cutoff
    except Exception:
        return True


# ── Per-entry processing ──────────────────────────────────────────────────────

def process(entry, r: str, feed_url: str, category: str) -> None:
    url = entry.get("link")
    if not url:
        return

    if retry_filter() and feed_url != retry_filter():
        return

    if not is_recent(entry):
        return

    if item_exists(url):
        return

    text = extract(url) or entry.get("summary", "")

    insert_item(
        generate_item_id(url, r),
        url,
        entry.get("title", ""),
        text,
        entry.get("published", r),
        r,
        category,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    r = run_id()

    for feed_url, category in load_feeds():
        # Skip YouTube feeds — handled by youtube.py
        if "youtube.com" in feed_url or "youtu.be" in feed_url:
            continue
        try:
            resp = requests.get(feed_url, timeout=30)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            for entry in feed.entries:
                try:
                    process(entry, r, feed_url, category)
                except Exception as ex:
                    insert_error(r, entry.get("link", feed_url), "parse", "unknown", str(ex))

        except Exception as ex:
            insert_error(r, feed_url, "fetch", "network", str(ex))


if __name__ == "__main__":
    main()
