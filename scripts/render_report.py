"""
render_report.py — Report monthly (1st of each month)
Email: title list only.
PDFs stored in report.db are written to /tmp/report_pdfs/ and attached by the workflow.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from db_utils import get_unpushed_reports, mark_pushed_report, run_id as new_run_id
from render_base import fmt_date, email_shell, section_heading, block_title_only, MUTED

ROOT        = Path(__file__).resolve().parent.parent
OUT_HTML    = ROOT / "out_report.html"
OUT_SUBJ    = ROOT / "out_report_subject.txt"
OUT_PDF_DIR = ROOT / "out_report_pdfs"
OUT_PDF_MANIFEST = ROOT / "out_report_pdf_manifest.json"
ISSUE_TYPE  = "report_monthly"


def main() -> None:
    issue_id = new_run_id()
    rows     = get_unpushed_reports(ISSUE_TYPE)
    if not rows:
        print("render_report: nothing to send")
        return

    # Write PDFs to disk for attachment
    OUT_PDF_DIR.mkdir(exist_ok=True)
    pdf_files: list[str] = []
    for row in rows:
        if row["pdf_data"]:
            safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (row["title"] or row["id"]))
            fname = f"{safe_title[:60]}.pdf"
            path  = OUT_PDF_DIR / fname
            path.write_bytes(row["pdf_data"])
            pdf_files.append(str(path))

    OUT_PDF_MANIFEST.write_text(json.dumps(pdf_files, indent=2))

    # Group by source for email
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        groups[row["source_name"]].append(row)

    parts = [
        f'<p style="margin:0 0 32px;font-size:13px;color:{MUTED}">'
        f'{len(rows)} reports this month'
        f'{f" · {len(pdf_files)} PDFs attached" if pdf_files else ""}'
        f'</p>'
    ]
    for src in sorted(groups):
        grp = groups[src]
        parts.append(section_heading(src, len(grp)))
        parts.append('<ul style="list-style:none;margin:0;padding:0">')
        for row in grp:
            parts.append(block_title_only(row["title"] or "", src, row["source_id"]))
        parts.append("</ul>")

    date_str = fmt_date()
    html_out = email_shell(
        title=f"Reports · {date_str}",
        subtitle=f"{len(rows)} reports · {len(pdf_files)} PDFs attached",
        body="\n".join(parts),
        issue_label="Report Monthly",
    )
    OUT_HTML.write_text(html_out, encoding="utf-8")
    OUT_SUBJ.write_text(f"Dewsletter Reports · {date_str} · {len(rows)} reports")

    for row in rows:
        mark_pushed_report(row["id"], ISSUE_TYPE, issue_id)
    print(f"render_report: {len(rows)} reports, {len(pdf_files)} PDFs → {OUT_HTML.name}")


if __name__ == "__main__":
    main()
