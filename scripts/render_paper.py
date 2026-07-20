"""render_paper.py — Paper weekly (every Friday) — title list only"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
from db_utils import get_unpushed, mark_pushed, run_id as new_run_id
from render_base import fmt_date, email_shell, section_heading, block_title_only

ROOT       = Path(__file__).resolve().parent.parent
OUT_HTML   = ROOT / "out_paper.html"
OUT_SUBJ   = ROOT / "out_paper_subject.txt"
ISSUE_TYPE = "paper_weekly"

LABELS: dict[str, str] = {
    "rss.daily.ai":           "AI Research",
    "rss.daily.economics":    "Economics",
    "rss.research.cs":        "Computer Science",
    "rss.research.science":   "Science",
    "rss.research.economics": "Finance & Economics",
}


def main() -> None:
    issue_id = new_run_id()
    rows     = get_unpushed("paper", ISSUE_TYPE)
    if not rows:
        print("render_paper: nothing to send")
        return

    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        groups[row["feed_key"]].append(row)

    parts = []
    for fk in sorted(groups):
        label = LABELS.get(fk, fk)
        grp   = groups[fk]
        parts.append(section_heading(label, len(grp)))
        parts.append('<ul style="list-style:none;margin:0;padding:0">')
        for row in grp:
            parts.append(block_title_only(row["title"] or "", row["source_name"], row["source_id"]))
        parts.append("</ul>")

    date_str = fmt_date()
    html_out = email_shell(
        title=f"Papers · {date_str}",
        subtitle=f"{len(rows)} papers — click titles to read",
        body="\n".join(parts),
        issue_label="Paper Weekly",
    )
    OUT_HTML.write_text(html_out, encoding="utf-8")
    OUT_SUBJ.write_text(f"Dewsletter Papers · {date_str} · {len(rows)} papers")

    for row in rows:
        mark_pushed("paper", row["id"], ISSUE_TYPE, issue_id)
    print(f"render_paper: {len(rows)} → {OUT_HTML.name}")


if __name__ == "__main__":
    main()
