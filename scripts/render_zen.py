"""render_zen.py — Zen weekly (every Sunday)"""
from __future__ import annotations
from pathlib import Path
from db_utils import get_unpushed, mark_pushed, run_id as new_run_id
from render_base import fmt_date, email_shell, section_heading, block_full, block_title_excerpt

ROOT       = Path(__file__).resolve().parent.parent
OUT_HTML   = ROOT / "out_zen.html"
OUT_SUBJ   = ROOT / "out_zen_subject.txt"
ISSUE_TYPE = "zen_weekly"


def main() -> None:
    issue_id = new_run_id()
    rows     = get_unpushed("zen", ISSUE_TYPE)
    if not rows:
        print("render_zen: nothing to send")
        return

    parts, prev_src = [], None
    for row in rows:
        src = row["source_name"]
        if src != prev_src:
            parts.append(section_heading(src))
            prev_src = src
            first = True
        else:
            first = False
        if row["display_mode"] == "full":
            parts.append(block_full(
                title=row["title"] or "", source_name=src, url=row["source_id"],
                content=row["content"] or "", read_minutes=row["read_minutes"] or 0,
                sep=not first,
            ))
        else:
            parts.append(block_title_excerpt(
                title=row["title"] or "", source_name=src, url=row["source_id"],
                content=row["content"] or "", sep=not first,
            ))

    date_str = fmt_date()
    html_out = email_shell(
        title=f"Zen · {date_str}",
        subtitle=f"{len(rows)} items",
        body="\n".join(parts),
        issue_label="Zen Weekly",
    )
    OUT_HTML.write_text(html_out, encoding="utf-8")
    OUT_SUBJ.write_text(f"Dewsletter Zen · {date_str} · {len(rows)} items")

    for row in rows:
        mark_pushed("zen", row["id"], ISSUE_TYPE, issue_id)
    print(f"render_zen: {len(rows)} → {OUT_HTML.name}")


if __name__ == "__main__":
    main()
