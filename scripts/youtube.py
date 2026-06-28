from datetime import datetime, UTC
from pathlib import Path
import xml.etree.ElementTree as ET
import os

import requests
import feedparser
import trafilatura

from db_write import insert_item, insert_error, item_exists
from hash import generate_item_id


OPML_PATH = Path("feed.opml")


def run_id():
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def retry_filter():
    return os.getenv("RETRY_ONLY_SOURCE")


def load_feeds():
    tree = ET.parse(OPML_PATH)
    root = tree.getroot()

    return [
        o.attrib["xmlUrl"]
        for o in root.iter("outline")
        if o.attrib.get("xmlUrl")
    ]


def fetch(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return feedparser.parse(r.content)


def extract(url):
    d = trafilatura.fetch_url(url)
    if not d:
        return None

    return trafilatura.extract(
        d,
        output_format="markdown"
    )


def content(entry):
    url = entry.get("link")

    if url:
        md = extract(url)
        if md:
            return md

    return entry.get("summary", "")


def process(entry, r, feed):
    url = entry.get("link")
    if not url:
        return

    if retry_filter() and feed != retry_filter():
        return

    if item_exists(url):
        return

    text = content(entry)

    insert_item(
        generate_item_id(url, r),
        url,
        entry.get("title", ""),
        text,
        entry.get("published", r),
        r,
    )


def main():
    r = run_id()

    for f in load_feeds():
        try:
            feed = fetch(f)

            for e in feed.entries:
                try:
                    process(e, r, f)
                except Exception as ex:
                    insert_error(r, e.get("link", f), "parse", "unknown", str(ex))

        except Exception as ex:
            insert_error(r, f, "fetch", "network", str(ex))


if __name__ == "__main__":
    main()
