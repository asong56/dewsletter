# Dewsletter

*dew* + *newsletter* — An RSS Operating System designed for inbox reading.

**Core question: if you only have 15 minutes today and the only thing you can open is your inbox, how does this email deliver maximum value?**

---

## Issues

| Issue | Schedule (BJT) | Content |
|-------|---------------|---------|
| **Daily** | Every day 04:00 | TLDR (full) · GitHub · Digest · HN (score > 350) · Billboard chart |
| **Dive Weekly** | Saturday 08:00 | Long-form full text: Noahpinion, Wait But Why, The Marginalian, etc. |
| **Zen Weekly** | Sunday 20:00 | sspai, Innei, Bubbles Town, Today I Found Out |
| **Paper Weekly** | Friday 08:00 | Title list: AI research, CS, science, economics papers |
| **Report Monthly** | 1st of month 08:00 | RAND, Brookings, NBER, Epoch AI, etc. — title list + PDFs attached |
| **YouTube Weekly** | Wednesday 08:00 | All channels — title list + subtitle status + `youtube.db` attached |

---

## Databases

All databases are tracked by **Git LFS** (see `.gitattributes`).

```
database/
├── core.db      — Daily: TLDR, GitHub, Digest, Billboard
├── hn.db        — HackerNews (score > 350, via Firebase API)
├── dive.db      — Long-form articles (full text)
├── zen.db       — Lifestyle articles (full text)
├── paper.db     — Papers: title + abstract only
├── report.db    — Think tank reports: title + PDF blob
└── youtube.db   — YouTube: video metadata + subtitle text
```

All content is **stored permanently**. Push history is tracked in the `push_log` table per database — content is never deleted on send.

---

## Feed Configuration

Feeds are split by content type:

| File | Content |
|------|---------|
| `feeds/rss.yaml` | All RSS/Atom sources |
| `feeds/hn.yaml` | HackerNews API config |
| `feeds/yt.yaml` | YouTube channel IDs |

Fill in all `FILL_ME` values before running.

---

## Display Protocols

| Mode | Used by | Renders |
|------|---------|---------|
| `full` | TLDR, Dive, Zen | Title + full text |
| `title_excerpt` | Digest, Bandcamp, sspai | Title + first ~180 chars + link |
| `title_only` | Papers, Reports | Title + source + link |
| `repo_card` | GitHub Trending | Repo name + one-line description |
| `chart_only` | Billboard | Rank table (scraped from billboard.com) |

---

## Setup

1. Fill `feeds/rss.yaml`, `feeds/yt.yaml` — replace all `FILL_ME` with real URLs / channel IDs
2. Set GitHub repository secrets:
   - `SMTP_USER` — Gmail address
   - `SMTP_PASS` — Gmail App Password
   - `TO_EMAIL` — recipient address
3. Enable Git LFS on your repo: `git lfs install`

---

## Local Testing

```bash
pip install feedparser requests trafilatura pyyaml yt-dlp

# Initialize all databases
python scripts/db_init.py

# Test daily ingest + render
python scripts/ingest_rss.py core
python scripts/ingest_hn.py
python scripts/render_daily.py
open out_daily.html
```

---

## Project Structure

```
dewsletter/
├── feeds/
│   ├── rss.yaml
│   ├── hn.yaml
│   └── yt.yaml
├── scripts/
│   ├── config.py
│   ├── db_init.py
│   ├── db_utils.py
│   ├── ingest_rss.py
│   ├── ingest_hn.py
│   ├── ingest_youtube.py
│   ├── render_base.py
│   ├── render_daily.py
│   ├── render_dive.py
│   ├── render_zen.py
│   ├── render_paper.py
│   ├── render_report.py
│   └── render_yt.py
├── database/              — all .db files (Git LFS)
├── schema.sql
├── .gitattributes         — database/*.db → LFS
└── .github/workflows/
    ├── daily.yml
    ├── dive_weekly.yml
    ├── zen_weekly.yml
    ├── paper_weekly.yml
    ├── report_monthly.yml
    └── yt_weekly.yml
```
