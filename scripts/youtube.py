"""
youtube.py  —  YouTube subtitle ingest
Changes from original:
  - Subtitles: English only (en / en-orig)
  - clean_vtt(): proper deduplication via seen-set, strips inline timing tags
  - process(): receives category from OPML; passes it to insert_item()
"""

from datetime import datetime, UTC
from pathlib import Path
import xml.etree.ElementTree as ET
import subprocess
import tempfile
import re
import os

import feedparser
import requests

from db_write import insert_item, insert_error, item_exists
from hash import generate_item_id


OPML_PATH = Path("feed.opml")


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def retry_filter() -> str | None:
    return os.getenv("RETRY_ONLY_SOURCE")


# ── OPML parsing ─────────────────────────────────────────────────────────────

def load_feeds() -> list[tuple[str, str]]:
    """Return (feed_url, category) pairs for YouTube feeds only."""
    tree  = ET.parse(OPML_PATH)
    feeds: list[tuple[str, str]] = []

    def walk(node: ET.Element, category: str = "") -> None:
        for child in node:
            if child.tag != "outline":
                continue
            url = child.attrib.get("xmlUrl", "")
            if url and ("youtube.com" in url or "youtu.be" in url):
                feeds.append((url, category))
            elif not url:
                walk(child, child.attrib.get("text", ""))

    body = tree.getroot().find("body")
    if body is not None:
        walk(body)

    return feeds


# ── Subtitle download ─────────────────────────────────────────────────────────

def download_vtt(url: str) -> str | None:
    """
    Download English subtitles (manual or auto-generated) for a YouTube URL.
    Returns raw VTT text or None if unavailable.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-sub",
            "--write-sub",
            "--sub-langs", "en,en-orig",
            "--sub-format", "vtt",
            "--output", f"{tmp}/%(id)s",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return None

        vtt_files = list(Path(tmp).glob("*.vtt"))
        if not vtt_files:
            return None

        return vtt_files[0].read_text("utf-8", errors="ignore")


def clean_vtt(vtt: str) -> str:
    """
    Convert WebVTT to clean plain text.

    YouTube auto-captions repeat previous lines in each cue during word-by-word
    reveals. A seen-set deduplicates these while preserving reading order.
    Inline timing tags like <00:00:01.500> and <c> / </c> are stripped.
    """
    seen: set[str] = set()
    lines: list[str] = []

    for block in re.split(r"\n\s*\n", vtt.strip()):
        for raw_line in block.splitlines():
            raw_line = raw_line.strip()

            # Skip VTT structure lines
            if (not raw_line
                    or "-->"        in raw_line
                    or raw_line.startswith("WEBVTT")
                    or raw_line.startswith("NOTE")
                    or raw_line.startswith("Kind:")
                    or raw_line.startswith("Language:")
                    or re.fullmatch(r"\d+", raw_line)):
                continue

            # Strip inline timing tags: <00:00:01.000>, <c>, </c>, <i>, </i>, etc.
            text = re.sub(r"<[^>]+>", "", raw_line).strip()

            if text and text not in seen:
                seen.add(text)
                lines.append(text)

    return " ".join(lines)


# ── Per-entry processing ──────────────────────────────────────────────────────

def process(entry, r: str, feed_url: str, category: str) -> None:
    url = entry.get("link")
    if not url:
        return

    if retry_filter() and feed_url != retry_filter():
        return

    if item_exists(url):
        return

    vtt = download_vtt(url)
    if not vtt:
        insert_error(r, url, "fetch", "network", "no subtitles available")
        return

    content = clean_vtt(vtt)
    if not content:
        insert_error(r, url, "parse", "format", "empty subtitle after cleaning")
        return

    insert_item(
        generate_item_id(url, r),
        url,
        entry.get("title", ""),
        content,
        entry.get("published", r),
        r,
        category,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    r = run_id()

    for feed_url, category in load_feeds():
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
