"""render_dive.py — Dive long-form weekly (every Saturday)"""
from __future__ import annotations
from pathlib import Path
from db_utils import get_unpushed, mark_pushed, run_id as new_run_id
from render_base import fmt_date, email_shell, section_heading, block_full

ROOT       = Path(__file__).resolve().parent.parent
OUT_HTML   = ROOT / "out_dive.html"
OUT_SUBJ   = ROOT / "out_dive_subject.txt"
ISSUE_TYPE = "dive_weekly"


def main() -> None:
    issue_id = new_run_id()
    rows     = get_unpushed("dive", ISSUE_TYPE)
    if not rows:
        print("render_dive: nothing to send")
        return

    total_min = sum(r["read_minutes"] or 0 for r in rows)
    parts, prev_src = [], None

    for row in rows:
        src = row["source_name"]
        if src != prev_src:
            parts.append(section_heading(src))
            prev_src = src
            first = True
        else:
            first = False
        parts.append(block_full(
            title=row["title"] or "", source_name=src, url=row["source_id"],
            content=row["content"] or "", read_minutes=row["read_minutes"] or 0,
            sep=not first,
        ))

    date_str = fmt_date()
    html_out = email_shell(
        title=f"Dive · {date_str}",
        subtitle=f"{len(rows)} long reads · ~{total_min} min",
        body="\n".join(parts),
        issue_label="Dive Weekly",
    )
    OUT_HTML.write_text(html_out, encoding="utf-8")
    OUT_SUBJ.write_text(f"Dewsletter Dive · {date_str} · {len(rows)} articles")

    for row in rows:
        mark_pushed("dive", row["id"], ISSUE_TYPE, issue_id)
    print(f"render_dive: {len(rows)} articles → {OUT_HTML.name}")


if __name__ == "__main__":
    main()
