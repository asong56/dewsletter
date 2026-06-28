from datetime import datetime, UTC
from pathlib import Path
import xml.etree.ElementTree as ET
import subprocess
import tempfile
import os

import feedparser
import requests

from db_write import insert_item, insert_error, item_exists
from hash import generate_item_id


def run_id():
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def retry_filter():
    return os.getenv("RETRY_ONLY_SOURCE")


def load_feeds():
    tree = ET.parse("feed.opml")
    return [
        o.attrib["xmlUrl"]
        for o in tree.iter("outline")
        if "youtube" in o.attrib.get("xmlUrl", "")
    ]


def extract_id(url):
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1]
    return None


def download(url):
    with tempfile.TemporaryDirectory() as t:
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-sub",
            "--sub-langs", "en.*,zh.*",
            "--output", f"{t}/%(id)s",
            url,
        ]

        r = subprocess.run(cmd)

        if r.returncode != 0:
            return None

        files = list(Path(t).glob("*.vtt"))
        if not files:
            return None

        return files[0].read_text("utf-8", errors="ignore")


def clean(vtt):
    return "\n".join(
        l for l in vtt.splitlines()
        if l and "-->" not in l and "WEBVTT" not in l and not l.isdigit()
    )


def process(entry, r, feed):
    url = entry.get("link")

    if retry_filter() and feed != retry_filter():
        return

    if item_exists(url):
        return

    vtt = download(url)

    if not vtt:
        insert_error(r, url, "fetch", "network", "subtitle fail")
        return

    insert_item(
        generate_item_id(url, r),
        url,
        entry.get("title", ""),
        clean(vtt),
        entry.get("published", r),
        r,
    )


def main():
    r = run_id()

    for f in load_feeds():
        try:
            feed = feedparser.parse(requests.get(f).content)

            for e in feed.entries:
                try:
                    process(e, r, f)
                except Exception as ex:
                    insert_error(r, e.get("link", f), "parse", "unknown", str(ex))

        except Exception as ex:
            insert_error(r, f, "fetch", "network", str(ex))


if __name__ == "__main__":
    main()