"""
youtube.py  —  YouTube subtitle ingest
字幕语言策略：下载视频原有的字幕（不强制英文），
优先手动字幕 > 自动生成，优先非英文（保留原语言）> 英文。
"""

from datetime import datetime, UTC
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
import subprocess
import tempfile
import re
import os

import feedparser
import requests

from db_write import insert_item, insert_error, item_exists
from hash import generate_item_id


OPML_PATH   = Path("feed.opml")
MAX_WORKERS = int(os.getenv("YT_WORKERS", "3"))


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

def pick_vtt(tmp_dir: Path) -> Path | None:
    """
    从下载目录选出最合适的 .vtt 文件。
    策略：有非英文字幕则优先选非英文（保留视频原语言）；
    全是英文时取第一个。
    """
    vtt_files = list(tmp_dir.glob("*.vtt"))
    if not vtt_files:
        return None

    # 非英文文件（原语言字幕）
    non_en = [
        f for f in vtt_files
        if not re.search(r"\.(en|en-orig|en-US|en-GB)[.-]", f.name)
        and not f.name.endswith(".en.vtt")
    ]
    return non_en[0] if non_en else vtt_files[0]


def download_vtt(url: str) -> str | None:
    """
    下载字幕：不限制语言，让 yt-dlp 下载视频本身有的字幕。
    优先手动字幕（--write-sub），fallback 自动生成（--write-auto-sub）。
    排除 live_chat 避免下载到直播弹幕记录。
    """
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-sub",
            "--write-auto-sub",
            "--sub-langs", "all,-live_chat",
            "--sub-format", "vtt",
            "--output", f"{tmp}/%(id)s",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return None

        chosen = pick_vtt(Path(tmp))
        if not chosen:
            return None

        return chosen.read_text("utf-8", errors="ignore")


def clean_vtt(vtt: str) -> str:
    """
    WebVTT → 纯文本。
    YouTube 自动字幕每个 cue 会重复前几行（逐词显示），用 seen-set 去重。
    去掉内联时间标签 <00:00:01.000>、<c>、</c> 等。
    """
    seen: set[str] = set()
    lines: list[str] = []

    for block in re.split(r"\n\s*\n", vtt.strip()):
        for raw_line in block.splitlines():
            raw_line = raw_line.strip()

            if (not raw_line
                    or "-->"        in raw_line
                    or raw_line.startswith("WEBVTT")
                    or raw_line.startswith("NOTE")
                    or raw_line.startswith("Kind:")
                    or raw_line.startswith("Language:")
                    or re.fullmatch(r"\d+", raw_line)):
                continue

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


# ── Per-feed processing（线程工作单元）────────────────────────────────────────

def fetch_feed(feed_url: str, category: str, r: str) -> None:
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


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    r = run_id()
    feeds = load_feeds()

    print(f"youtube: {len(feeds)} channels, {MAX_WORKERS} workers")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {exe.submit(fetch_feed, url, cat, r): url for url, cat in feeds}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as ex:
                print(f"[unhandled] {futures[future]}: {ex}")


if __name__ == "__main__":
    main()
