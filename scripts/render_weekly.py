"""
render_weekly.py
Reads all items from current.db and produces:
  - weekly.html        Single-page reading archive (browser-native CSS)
  - weekly_subject.txt Subject line for the workflow

Structure:
  Header (title, week range, stats)
  Layout: sticky TOC  |  Main content
    TOC: Category → Day entries + Feed Health link
    Main: <section per category> → <section per day> → <article>
    Feed Health table (from archive.db if available)

Design system: asong56 Design Manual v0.3
"""

from pathlib import Path
import sqlite3
import html
import re
import sys
from datetime import datetime
from urllib.parse import urlparse
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from archive import feed_health
    _HAS_ARCHIVE = True
except ImportError:
    _HAS_ARCHIVE = False

try:
    import markdown as md_lib
    def _md(text: str) -> str:
        out = md_lib.markdown(text or "", extensions=["extra", "sane_lists"])
        out = re.sub(r"<img[^>]*/?>", "", out)
        out = re.sub(r"<script[^>]*>.*?</script>", "", out, flags=re.DOTALL)
        return out
except ImportError:
    def _md(text: str) -> str:
        return "<p>" + html.escape(text or "") + "</p>"

ROOT        = Path(__file__).resolve().parent.parent
DB_PATH     = ROOT / "current.db"
OUT_HTML    = ROOT / "weekly.html"
OUT_SUBJECT = ROOT / "weekly_subject.txt"


# ── Design-system CSS (plain string — CSS braces are literals) ────────────────

CSS = """
/* ── Reset ──────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; }

/* ── Color tokens §2.4 ───────────────────────────────────────── */
:root {
  --color-bg:           oklch(98.5% 0.003 260);
  --color-surface:      oklch(95%   0.004 260);
  --color-border:       oklch(88%   0.005 260);
  --color-text-muted:   oklch(60%   0.008 260);
  --color-text:         oklch(28%   0.008 260);
  --color-accent:       oklch(52%   0.18  220);
  --color-accent-dim:   oklch(96%   0.04  220);

  --text-xs:   0.75rem;
  --text-sm:   0.875rem;
  --text-base: 1rem;
  --text-lg:   1.25rem;
  --text-xl:   1.625rem;
  --text-2xl:  2.5rem;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg:           oklch(11%  0.003 260);
    --color-surface:      oklch(16%  0.004 260);
    --color-border:       oklch(24%  0.005 260);
    --color-text-muted:   oklch(60%  0.008 260);
    --color-text:         oklch(88%  0.008 260);
    --color-accent:       oklch(60%  0.16  220);
    --color-accent-dim:   oklch(18%  0.06  220);
  }
}

/* ── Base ────────────────────────────────────────────────────── */
html { scrollbar-gutter: stable; scroll-behavior: smooth; background: var(--color-bg); }

body {
  font-family:
    'OPPO Sans', 'PingFang SC', 'Microsoft YaHei',
    'Switzer', 'Open Sans', ui-sans-serif, system-ui, sans-serif;
  font-size: var(--text-base);
  line-height: 1.7;
  letter-spacing: 0.02em;
  color: var(--color-text);
  background: var(--color-bg);
}

/* ── Scrollbar §13.2 ─────────────────────────────────────────── */
* { scrollbar-width: thin; scrollbar-color: transparent transparent; }
*:hover { scrollbar-color: var(--color-border) transparent; }
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track  { background: transparent; }
::-webkit-scrollbar-corner { background: transparent; }
::-webkit-scrollbar-thumb  { background: transparent; border-radius: 50px; }
*:hover::-webkit-scrollbar-thumb { background: var(--color-border); }
::-webkit-scrollbar-thumb:hover  { background: var(--color-text-muted); }

/* ── Selection §13.3 ─────────────────────────────────────────── */
::selection          { background: var(--color-accent-dim); color: inherit; }
pre ::selection,
code ::selection     { background: oklch(52% 0.18 220 / 0.25); }

/* ── Typography §3 ───────────────────────────────────────────── */
h1 { font-size: var(--text-2xl); font-weight: 600; line-height: 1.1; letter-spacing: -.03em; margin: 0 0 24px; }
h2 { font-size: var(--text-xl);  font-weight: 600; line-height: 1.2; letter-spacing: -.02em; margin: 48px 0 16px; }
h3 { font-size: var(--text-lg);  font-weight: 600; line-height: 1.3; letter-spacing: -.01em; margin: 32px 0 8px; }
p  { margin: 0 0 16px; }
li { margin-bottom: 8px; }

/* ── Links §3.7 ──────────────────────────────────────────────── */
a {
  color: inherit;
  text-decoration-color: var(--color-border);
  text-underline-offset: 3px;
  transition:
    color                 120ms cubic-bezier(0.25, 0.46, 0.45, 0.94),
    text-decoration-color 120ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
a:hover { color: var(--color-accent); text-decoration-color: var(--color-accent); }
a[href^="http"]::after {
  content: '↗';
  font-size: 0.7em; vertical-align: super; margin-left: 0.1em; display: inline-block;
  transition: transform 120ms cubic-bezier(0.34, 1.56, 0.64, 1.0);
}
a[href^="http"]:hover::after { transform: translate(2px, -2px); }

/* ── Page layout ─────────────────────────────────────────────── */
.site-header {
  max-width: 1100px; margin: 0 auto;
  padding: 48px 32px 32px;
  border-bottom: 1px solid var(--color-border);
}
.site-header .label {
  margin: 0 0 10px;
  font-size: var(--text-xs); font-weight: 600;
  letter-spacing: .10em; text-transform: uppercase;
  color: var(--color-text-muted);
}
.site-header .meta {
  margin: 12px 0 0;
  font-size: var(--text-sm); color: var(--color-text-muted); line-height: 1.5;
}

.layout {
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr);
  gap: 0 48px;
  max-width: 1100px; margin: 0 auto;
  padding: 48px 32px 96px;
  align-items: start;
}

/* ── TOC ──────────────────────────────────────────────────────── */
nav.toc {
  position: sticky; top: 24px; align-self: start;
  max-height: calc(100vh - 48px); overflow-y: auto;
  padding-right: 8px;
}
nav.toc a::after { display: none; }

.toc-section { margin-bottom: 20px; }

.toc-cat {
  display: block;
  font-size: var(--text-xs); font-weight: 600;
  letter-spacing: .08em; text-transform: uppercase;
  color: var(--color-text-muted);
  padding: 4px 8px 6px;
  user-select: none;
}

.toc-section ol {
  list-style: none; margin: 0; padding: 0;
  display: flex; flex-direction: column; gap: 1px;
}

.toc-section a {
  display: flex; align-items: center; justify-content: space-between;
  font-size: var(--text-sm); color: var(--color-text-muted);
  text-decoration: none; padding: 4px 8px; border-radius: 6px; line-height: 1.4;
  transition:
    background-color 120ms cubic-bezier(0.25, 0.46, 0.45, 0.94),
    color            120ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.toc-section a:hover { color: var(--color-text); background: var(--color-surface); }
.toc-section a small { font-size: var(--text-xs); opacity: .6; flex-shrink: 0; margin-left: 6px; }

.toc-health { margin-top: 8px; }
.toc-health a {
  font-size: var(--text-xs); color: var(--color-text-muted);
  text-decoration: none; padding: 4px 8px; border-radius: 6px; display: block;
  transition: background-color 120ms, color 120ms;
}
.toc-health a:hover { color: var(--color-text); background: var(--color-surface); }

/* ── Main ────────────────────────────────────────────────────── */
main { max-width: 68ch; }

/* ── Category section ────────────────────────────────────────── */
.cat-section + .cat-section { margin-top: 72px; }
.cat-section > h2 {
  font-size: var(--text-sm); font-weight: 600;
  letter-spacing: .08em; text-transform: uppercase;
  color: var(--color-text-muted);
  margin: 0 0 32px; padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border);
  user-select: none;
}

/* ── Day section ─────────────────────────────────────────────── */
.day-section + .day-section { margin-top: 48px; }
.day-section > h3 {
  font-size: var(--text-xs); font-weight: 600;
  letter-spacing: .08em; text-transform: uppercase;
  color: var(--color-text-muted); margin: 0 0 20px;
  user-select: none;
}

/* ── Article list §8.2 ───────────────────────────────────────── */
article + article { border-top: 1px solid var(--color-border); padding-top: 24px; margin-top: 24px; }
article {
  transition:
    background-color 120ms cubic-bezier(0.25, 0.46, 0.45, 0.94),
    padding          120ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
article:hover {
  background-color: var(--color-surface);
  padding-inline: 12px; margin-inline: -12px; border-radius: 8px;
}
article > header { margin-bottom: 12px; }
article h4 {
  margin: 0 0 6px; font-size: var(--text-lg); font-weight: 600;
  line-height: 1.3; letter-spacing: -.01em;
}
article h4 a { text-decoration: none; }
article h4 a:hover { color: var(--color-accent); }

.art-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0; }

/* Badge §8.3 */
.badge {
  display: inline-flex; align-items: center;
  font-size: var(--text-xs);
  font-family: ui-monospace, 'Monaspace Neon', monospace;
  font-weight: 600; letter-spacing: .06em;
  border-radius: 4px; padding: 2px 6px;
  color: var(--color-text-muted); border: 1px solid var(--color-border);
  background: transparent; user-select: none;
}

.art-body { font-size: var(--text-base); line-height: 1.7; }
.art-body > *:last-child { margin-bottom: 0; }
.art-body h1,.art-body h2,.art-body h3,.art-body h4 { font-weight: 600; margin: 24px 0 8px; }
.art-body code {
  font-family: ui-monospace, 'Monaspace Neon', monospace;
  font-size: .875em; background: var(--color-surface);
  border-radius: 4px; padding: 1px 5px;
}
.art-body pre {
  background: var(--color-surface); border-radius: 8px; padding: 16px;
  overflow-x: auto; font-size: .875rem; line-height: 1.6; margin: 16px 0;
}
.art-body pre code { background: none; padding: 0; }
.art-body blockquote {
  margin: 16px 0; padding-left: 16px;
  border-left: 2px solid var(--color-border);
  color: var(--color-text-muted); font-style: italic;
}

/* ── Feed health ─────────────────────────────────────────────── */
.health-section {
  margin-top: 72px; padding-top: 32px;
  border-top: 1px solid var(--color-border);
}
.health-section > h2 {
  font-size: var(--text-sm); font-weight: 600;
  letter-spacing: .08em; text-transform: uppercase;
  color: var(--color-text-muted); margin: 0 0 24px; user-select: none;
}

.health-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
.health-table th {
  text-align: left;
  font-size: var(--text-xs); font-weight: 600;
  letter-spacing: .06em; text-transform: uppercase;
  color: var(--color-text-muted);
  padding: 0 12px 10px 0;
  border-bottom: 1px solid var(--color-border);
  user-select: none;
}
.health-table td {
  padding: 10px 12px 10px 0;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text); vertical-align: middle; line-height: 1.4;
}
.health-table tr:last-child td { border-bottom: none; }
.health-table .col-url { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.health-table .col-url a {
  text-decoration: none;
  font-family: ui-monospace, monospace; font-size: var(--text-xs);
}
.health-table .col-url a::after { display: none; }
.health-table .col-url a:hover { color: var(--color-accent); }
.health-table .col-count { color: var(--color-text-muted); text-align: right; padding-right: 24px; }

.status { display: inline-flex; align-items: center; gap: 6px; font-size: var(--text-xs); white-space: nowrap; }
.status::before { content: ''; display: inline-block; width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.status.green::before { background: oklch(55% 0.18 145); }
.status.amber::before { background: oklch(72% 0.18  55); }
.status.red::before   { background: oklch(52% 0.18  25); }
.status.grey::before  { background: var(--color-border); }

/* ── Site footer ──────────────────────────────────────────────── */
.site-footer { max-width: 1100px; margin: 0 auto; padding: 24px 32px 48px; border-top: 1px solid var(--color-border); }
.site-footer p { margin: 0; font-size: var(--text-xs); color: var(--color-text-muted); line-height: 1.6; }

/* ── Reduced motion §6.5 ─────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
}

/* ── Mobile §10 ──────────────────────────────────────────────── */
@media (max-width: 768px) {
  .site-header { padding: 32px 16px 24px; }
  .layout { grid-template-columns: 1fr; padding: 24px 16px 64px; gap: 0; }
  nav.toc { position: static; max-height: none; overflow: visible; margin-bottom: 32px; padding-bottom: 24px; padding-right: 0; border-bottom: 1px solid var(--color-border); }
  .toc-section ol { flex-direction: row; flex-wrap: wrap; gap: 4px; }
  h1 { font-size: var(--text-xl); }
  .health-table .col-url { max-width: 120px; }
}
"""


# ── DB helpers ────────────────────────────────────────────────────────────────

def all_items(conn: sqlite3.Connection) -> list:
    return conn.execute(
        "SELECT id, title, source_id, content, created_at, run_id, category "
        "FROM items ORDER BY run_id ASC, created_at ASC"
    ).fetchall()


# ── Data helpers ──────────────────────────────────────────────────────────────

def day_key(run_id: str) -> str:
    return run_id[:8]


def day_label(key: str) -> str:
    try:
        dt   = datetime.strptime(key, "%Y%m%d")
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        return dt.strftime(f"%b %d · {days[dt.weekday()]}")
    except Exception:
        return key


def cat_anchor(cat: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", cat.lower()).strip("-")
    return f"cat-{slug or 'uncategorized'}"


def day_anchor(cat: str, day: str) -> str:
    return f"{cat_anchor(cat)}-{day}"


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return url


def week_range(rows: list) -> str:
    keys = sorted({r[5][:8] for r in rows})
    if not keys:
        return ""
    try:
        first = datetime.strptime(keys[0],  "%Y%m%d")
        last  = datetime.strptime(keys[-1], "%Y%m%d")
        return f"{first.strftime('%Y · %b %d')} — {last.strftime('%b %d')}"
    except Exception:
        return ""


def group_items(rows: list) -> dict:
    """Returns {category: {day_key: [row, ...]}} sorted by category then day."""
    buckets: dict = defaultdict(lambda: defaultdict(list))
    for row in rows:
        cat = row[6] or "Uncategorized"
        buckets[cat][day_key(row[5])].append(row)
    return {
        cat: dict(sorted(days.items()))
        for cat, days in sorted(buckets.items())
    }


# ── HTML rendering ────────────────────────────────────────────────────────────

def render_article(row) -> str:
    _, title, source_id, content, *_ = row
    t   = html.escape(title or "(untitled)")
    src = html.escape(domain(source_id))
    url = html.escape(source_id)
    return (
        f'<article>'
        f'<header>'
        f'<h4><a href="{url}">{t}</a></h4>'
        f'<p class="art-meta"><span class="badge">{src}</span></p>'
        f'</header>'
        f'<div class="art-body">{_md(content)}</div>'
        f'</article>'
    )


def render_main(grouped: dict) -> str:
    out = []
    for cat, days in grouped.items():
        ca        = cat_anchor(cat)
        day_secs  = []
        for dk, items in days.items():
            arts = "\n".join(render_article(r) for r in items)
            day_secs.append(
                f'<div class="day-section" id="{day_anchor(cat, dk)}">'
                f'<h3>{html.escape(day_label(dk))} · {len(items)}</h3>'
                f'{arts}'
                f'</div>'
            )
        out.append(
            f'<section class="cat-section" id="{ca}">'
            f'<h2>{html.escape(cat)}</h2>'
            + "\n".join(day_secs)
            + '</section>'
        )
    return "\n\n".join(out)


def render_toc(grouped: dict, has_health: bool) -> str:
    parts = []
    for cat, days in grouped.items():
        ca    = cat_anchor(cat)
        rows  = "".join(
            f'<li><a href="#{day_anchor(cat, dk)}">'
            f'{html.escape(day_label(dk))}'
            f'<small>{len(items)}</small>'
            f'</a></li>'
            for dk, items in days.items()
        )
        parts.append(
            f'<div class="toc-section">'
            f'<a class="toc-cat" href="#{ca}">{html.escape(cat)}</a>'
            f'<ol>{rows}</ol>'
            f'</div>'
        )
    if has_health:
        parts.append(
            '<div class="toc-section toc-health">'
            '<a href="#feed-health">Feed Health</a>'
            '</div>'
        )
    return f'<nav class="toc" aria-label="Contents">{"".join(parts)}</nav>'


_STATUS_LABEL = {"green": "Active", "amber": "Slow", "red": "Stale", "grey": "Never"}


def render_health(health: list) -> str:
    if not health:
        return ""
    rows = []
    for f in health:
        url  = html.escape(f["url"])
        src  = html.escape(domain(f["url"]))
        cat  = html.escape(f["category"])
        ago  = f'{f["days_ago"]}d ago' if f["days_ago"] is not None else "—"
        st   = f["status"]
        rows.append(
            f'<tr>'
            f'<td class="col-url"><a href="{url}" title="{url}">{src}</a></td>'
            f'<td>{cat}</td>'
            f'<td><span class="status {st}">{_STATUS_LABEL[st]}</span></td>'
            f'<td>{ago}</td>'
            f'<td class="col-count">{f["total"]}</td>'
            f'</tr>'
        )
    return (
        f'<section class="health-section" id="feed-health">'
        f'<h2>Feed Health</h2>'
        f'<table class="health-table">'
        f'<thead><tr>'
        f'<th>Source</th><th>Category</th><th>Status</th>'
        f'<th>Last article</th><th style="text-align:right">Total</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
        f'</section>'
    )


def render_page(rows: list, grouped: dict, health: list) -> str:
    week = week_range(rows)
    now  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>nodeu2c Weekly · {html.escape(week)}</title>
<style>{CSS}</style>
</head>
<body>

<header class="site-header">
  <p class="label">nodeu2c Weekly</p>
  <h1>{html.escape(week)}</h1>
  <p class="meta">{len(rows)} articles · {len(grouped)} categories · generated {now}</p>
</header>

<div class="layout">
  {render_toc(grouped, bool(health))}
  <main>
    {render_main(grouped)}
    {render_health(health)}
  </main>
</div>

<footer class="site-footer">
  <p>nodeu2c · GitHub Actions · RSS &amp; YouTube subtitle ingest</p>
</footer>

</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = all_items(conn)
    finally:
        conn.close()

    grouped = group_items(rows)

    health: list = []
    if _HAS_ARCHIVE:
        try:
            health = feed_health()
        except Exception as ex:
            print(f"feed health skipped: {ex}")

    OUT_HTML.write_text(render_page(rows, grouped, health), encoding="utf-8")

    week = week_range(rows)
    OUT_SUBJECT.write_text(
        f"Weekly · {week} · {len(rows)} articles · {len(grouped)} categories"
    )
    print(f"render_weekly: {len(rows)} articles, {len(grouped)} categories → {OUT_HTML.name}")


if __name__ == "__main__":
    main()
