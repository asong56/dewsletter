"""
config.py — Load feeds from feeds/rss.yaml, feeds/hn.yaml, feeds/yt.yaml
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml

ROOT      = Path(__file__).resolve().parent.parent
FEEDS_DIR = ROOT / "feeds"
DB_DIR    = ROOT / "database"

# Daily section render order (lower = higher up in email)
DAILY_ORDER: dict[str, int] = {
    "rss.daily.tech":         1,
    "rss.daily.github":       2,
    "rss.digest.ai":          3,
    "rss.digest.engineering":  4,
    "rss.digest.economics":   5,
    "rss.digest.podcast":     6,
    "hn":                     7,
    "rss.daily.music":        8,
}


def _load(filename: str) -> dict[str, Any]:
    path = FEEDS_DIR / filename
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def rss_feeds() -> list[dict[str, Any]]:
    return _load("rss.yaml").get("feeds", [])


def hn_config() -> dict[str, Any]:
    return _load("hn.yaml").get("hn", {})


def yt_feeds() -> list[dict[str, Any]]:
    return _load("yt.yaml").get("feeds", [])


def rss_feeds_for_db(db: str) -> list[dict[str, Any]]:
    return [g for g in rss_feeds() if g.get("db") == db]


def db_path(name: str) -> Path:
    return DB_DIR / f"{name}.db"
