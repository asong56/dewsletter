"""
ingest_youtube.py — YouTube subtitle ingest
Reads feeds/yt.yaml, fetches video lists via YouTube RSS feed,
downloads subtitles with yt-dlp, stores in youtube.db.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, UTC
from pathlib import Path

import feedparser
import requests

from config import yt_feeds
from db_utils import run_id, yt_exists, insert_yt, insert_error as _err, now_iso

MAX_WORKERS   = int(os.getenv("YT_WORKERS", "3"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "8"))
RETRY_SOURCE  = os.getenv("RETRY_ONLY_SOURCE")


def yt_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def is_recent(entry) -> bool:
    pub = entry.get("published_parsed")
    if pub is None:
        return True
    try:
        return datetime(*pub[:6], tzinfo=UTC) >= datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
    except Exception:
        return True


def pick_vtt(tmp_dir: Path) -> Path | None:
    vtt_files = list(tmp_dir.glob("*.vtt"))
    if not vtt_files:
        return None
    non_en = [
        f for f in vtt_files
        if not re.search(r"\.(en|en-orig|en-US|en-GB)[.-]", f.name)
        and not f.name.endswith(".en.vtt")
    ]
    return non_en[0] if non_en else vtt_files[0]


def download_subtitle(video_url: str) -> str | None:
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "yt-dlp", "--skip-download",
            "--write-sub", "--write-auto-sub",
            "--sub-langs", "all,-live_chat",
            "--sub-format", "vtt",
            "--output", f"{tmp}/%(id)s",
            video_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return None
        chosen = pick_vtt(Path(tmp))
        return chosen.read_text("utf-8", errors="ignore") if chosen else None


def clean_vtt(vtt: str) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for block in re.split(r"\n\s*\n", vtt.strip()):
        for raw in block.splitlines():
            raw = raw.strip()
            if (not raw or "-->" in raw or raw.startswith(("WEBVTT", "NOTE", "Kind:", "Language:"))
                    or re.fullmatch(r"\d+", raw)):
                continue
            text = re.sub(r"<[^>]+>", "", raw).strip()
            if text and text not in seen:
                seen.add(text)
                lines.append(text)
    return " ".join(lines)


def insert_error(r: str, source_id: str, stage: str, msg: str) -> None:
    _err("youtube", run_id=r, source_id=source_id,
         stage=stage, error_type="unknown", message=msg)


def process_entry(entry, *, channel_id: str, channel_name: str,
                  feed_key: str, r: str) -> None:
    video_url = entry.get("link", "")
    if not video_url:
        return
    if RETRY_SOURCE and channel_id != RETRY_SOURCE:
        return
    if not is_recent(entry):
        return
    if yt_exists(video_url):
        return

    video_id = entry.get("yt_videoid") or ""
    if not video_id:
        m = re.search(r"v=([^&]+)", video_url)
        video_id = m.group(1) if m else ""

    vtt      = download_subtitle(video_url)
    subtitle = clean_vtt(vtt) if vtt else None

    insert_yt(
        video_url=video_url, video_id=video_id,
        channel_id=channel_id, channel_name=channel_name,
        feed_key=feed_key, title=entry.get("title", ""),
        subtitle=subtitle, published_at=entry.get("published", r),
    )
    status = "subtitle OK" if subtitle else "no subtitle"
    print(f"  [{channel_name}] {entry.get('title', '')[:55]} — {status}")


def fetch_channel(channel_id: str, channel_name: str, feed_key: str, r: str) -> None:
    url = yt_feed_url(channel_id)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            try:
                process_entry(entry, channel_id=channel_id, channel_name=channel_name,
                              feed_key=feed_key, r=r)
            except Exception as ex:
                insert_error(r, entry.get("link", url), "parse", str(ex))
    except Exception as ex:
        insert_error(r, url, "fetch", str(ex))


def main() -> None:
    r     = run_id()
    tasks = []
    for group in yt_feeds():
        feed_key = group["key"]
        for src in group.get("sources", []):
            cid = src.get("channel_id", "")
            if not cid or cid == "FILL_ME":
                continue
            tasks.append(dict(channel_id=cid, channel_name=src["name"], feed_key=feed_key))

    print(f"ingest_youtube: {len(tasks)} channels, {MAX_WORKERS} workers")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {
            exe.submit(fetch_channel, t["channel_id"], t["channel_name"], t["feed_key"], r): t
            for t in tasks
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as ex:
                print(f"[unhandled] {futures[future]['channel_name']}: {ex}")

    print("ingest_youtube: done")


if __name__ == "__main__":
    main()
