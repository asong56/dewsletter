"""
render_daily.py — Daily digest renderer
Section order: TLDR → GitHub → Digest → HN → Billboard/Bandcamp
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, UTC
from pathlib import Path

from config import DAILY_ORDER
from db_utils import get_unpushed, get_unpushed_hn, mark_pushed, mark_pushed_hn, run_id as new_run_id
from render_base import (
    fmt_date, email_shell, section_heading,
    block_full, block_title_excerpt, block_repo_card, block_hn, chart_table, MUTED,
)

ROOT       = Path(__file__).resolve().parent.parent
OUT_HTML   = ROOT / "out_daily.html"
OUT_SUBJ   = ROOT / "out_daily_subject.txt"
ISSUE_TYPE = "daily"


def render_rss_sections(rows) -> tuple[str, int, int]:
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        groups[row["feed_key"]].append(row)

    def order(k: str) -> int:
        for prefix, v in DAILY_ORDER.items():
            if k.startswith(prefix):
                return v
        return 99

    parts, total_count, total_minutes = [], 0, 0

    for fk in sorted(groups, key=order):
        grp = groups[fk]
        parts.append(section_heading(grp[0]["source_name"], len(grp)))
        for i, row in enumerate(grp):
            mode = row["display_mode"]
            kw   = dict(title=row["title"] or "", source_name=row["source_name"],
                        url=row["source_id"], content=row["content"] or "", sep=(i > 0))
            if mode == "full":
                parts.append(block_full(**kw, read_minutes=row["read_minutes"] or 0))
            elif mode == "repo_card":
                parts.append(block_repo_card(**kw))
            elif mode == "chart_only":
                parts.append(chart_table(row["content"] or ""))
            else:
                parts.append(block_title_excerpt(**kw))
            total_count   += 1
            total_minutes += row["read_minutes"] or 0

    return "\n".join(parts), total_count, total_minutes


def render_hn_section(hn_rows) -> str:
    if not hn_rows:
        return ""
    parts = [section_heading("Hacker News", len(hn_rows)),
             f'<ul style="list-style:none;margin:0;padding:0">']
    for row in hn_rows:
        parts.append(block_hn(
            title=row["title"], url=row["url"] or row["source_id"],
            score=row["score"], by=row["by"] or "",
            descendants=row["descendants"] or 0, hn_url=row["source_id"],
        ))
    parts.append("</ul>")
    return "\n".join(parts)


def main() -> None:
    issue_id = new_run_id()
    rss_rows = get_unpushed("core", ISSUE_TYPE)
    hn_rows  = get_unpushed_hn(ISSUE_TYPE)

    rss_html, rss_count, rss_minutes = render_rss_sections(rss_rows)
    hn_html  = render_hn_section(hn_rows)
    total    = rss_count + len(hn_rows)

    summary = (
        f'<p style="margin:0 0 32px;font-size:13px;color:{MUTED};line-height:1.6">'
        f'{total} items &middot; ~{rss_minutes} min read</p>'
    )

    date_str = fmt_date()
    html_out = email_shell(
        title=date_str,
        subtitle=f"{total} items · ~{rss_minutes} min read",
        body=summary + rss_html + hn_html,
        issue_label="Daily",
    )
    OUT_HTML.write_text(html_out, encoding="utf-8")
    OUT_SUBJ.write_text(f"Dewsletter Daily · {date_str} · {total} items")

    for row in rss_rows:
        mark_pushed("core", row["id"], ISSUE_TYPE, issue_id)
    for row in hn_rows:
        mark_pushed_hn(row["id"], ISSUE_TYPE, issue_id)

    print(f"render_daily: {rss_count} RSS + {len(hn_rows)} HN → {OUT_HTML.name}")


if __name__ == "__main__":
    main()
