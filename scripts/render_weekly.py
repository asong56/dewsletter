from pathlib import Path
import sqlite3
import html
import re
from datetime import datetime
from urllib.parse import urlparse
from collections import defaultdict

try:
    import markdown as md_lib
    def _md(text: str) -> str:
        out = md_lib.markdown(text or "", extensions=["extra", "sane_lists"])
        # strip broken offline images
        out = re.sub(r'<img[^>]*/?>',  '', out)
        out = re.sub(r'<script[^>]*>.*?</script>', '', out, flags=re.DOTALL)
        return out
except ImportError:
    def _md(text: str) -> str:
        return f"<p>{html.escape(text or '')}</p>"

ROOT        = Path(__file__).resolve().parent.parent
DB_PATH     = ROOT / "current.db"
OUT_HTML    = ROOT / "weekly.html"
OUT_SUBJECT = ROOT / "weekly_subject.txt"


# ── Design system CSS (§2 – §13, asong56 Design Manual) ─────────────────────
# Plain string — braces are CSS, not f-string expressions.

CSS = """
/* ── Reset ─────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; }

/* ── Color tokens §2.4 ──────────────────────────────────────── */
:root {
  --color-bg:         oklch(98.5% 0.003 260);
  --color-surface:    oklch(95%   0.004 260);
  --color-border:     oklch(88%   0.005 260);
  --color-text-muted: oklch(60%   0.008 260);
  --color-text:       oklch(28%   0.008 260);
  --color-accent:     oklch(52%   0.18  220);
  --color-accent-dim: oklch(96%   0.04  220);

  --text-xs:   0.75rem;
  --text-sm:   0.875rem;
  --text-base: 1rem;
  --text-lg:   1.25rem;
  --text-xl:   1.625rem;
  --text-2xl:  2.5rem;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg:         oklch(11%  0.003 260);
    --color-surface:    oklch(16%  0.004 260);
    --color-border:     oklch(24%  0.005 260);
    --color-text-muted: oklch(60%  0.008 260);
    --color-text:       oklch(88%  0.008 260);
    --color-accent:     oklch(60%  0.16  220);
    --color-accent-dim: oklch(18%  0.06  220);
  }
}

/* ── Base ───────────────────────────────────────────────────── */
html {
  scrollbar-gutter: stable;
  scroll-behavior: smooth;
  background: var(--color-bg);
}

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

/* ── Scrollbar §13.2 ────────────────────────────────────────── */
* {
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
*:hover {
  scrollbar-color: var(--color-border) transparent;
}
::-webkit-scrollbar          { width: 5px; height: 5px; }
::-webkit-scrollbar-track    { background: transparent; }
::-webkit-scrollbar-corner   { background: transparent; }
::-webkit-scrollbar-thumb    { background: transparent; border-radius: 50px; }
*:hover::-webkit-scrollbar-thumb       { background: var(--color-border); }
::-webkit-scrollbar-thumb:hover        { background: var(--color-text-muted); }
::-webkit-scrollbar-thumb:active       { background: var(--color-text-muted); }

/* ── Selection §13.3 ────────────────────────────────────────── */
::selection               { background: var(--color-accent-dim); color: inherit; }
pre ::selection,
code ::selection          { background: oklch(52% 0.18 220 / 0.25); }
blockquote ::selection    { background: var(--color-accent-dim); color: inherit; }

/* ── Typography §3 ──────────────────────────────────────────── */
h1 {
  font-size: var(--text-2xl); font-weight: 600;
  line-height: 1.1; letter-spacing: -0.03em;
  margin: 0 0 24px;
}
h2 {
  font-size: var(--text-xl); font-weight: 600;
  line-height: 1.2; letter-spacing: -0.02em;
  margin: 48px 0 16px;
}
h3 {
  font-size: var(--text-lg); font-weight: 600;
  line-height: 1.3; letter-spacing: -0.01em;
  margin: 32px 0 8px;
}
p  { margin: 0 0 16px; }
li { margin-bottom: 8px; }

/* ── Links §3.7 ─────────────────────────────────────────────── */
a {
  color: inherit;
  text-decoration-color: var(--color-border);
  text-underline-offset: 3px;
  transition:
    color                 120ms cubic-bezier(0.25, 0.46, 0.45, 0.94),
    text-decoration-color 120ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
a:hover {
  color: var(--color-accent);
  text-decoration-color: var(--color-accent);
}
a[href^="http"]::after {
  content: '↗';
  font-size: 0.7em;
  vertical-align: super;
  margin-left: 0.1em;
  display: inline-block;
  transition: transform 120ms cubic-bezier(0.34, 1.56, 0.64, 1.0);
}
a[href^="http"]:hover::after { transform: translate(2px, -2px); }

/* ── Page layout ────────────────────────────────────────────── */
.site-header {
  max-width: 1100px;
  margin: 0 auto;
  padding: 48px 32px 32px;
  border-bottom: 1px solid var(--color-border);
}

.site-header p.label {
  margin: 0 0 10px;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.site-header p.meta {
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  line-height: 1.5;
}

.layout {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 0 48px;
  max-width: 1100px;
  margin: 0 auto;
  padding: 48px 32px 96px;
  align-items: start;
}

/* ── TOC ────────────────────────────────────────────────────── */
nav.toc {
  position: sticky;
  top: 24px;
  align-self: start;
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  padding-right: 8px;
}

nav.toc a::after { display: none; } /* suppress ↗ in TOC */

nav.toc > p {
  margin: 0 0 12px;
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  user-select: none;
}

nav.toc ol {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

nav.toc a {
  display: block;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  text-decoration: none;
  padding: 5px 8px;
  border-radius: 6px;
  line-height: 1.4;
  transition:
    background-color 120ms cubic-bezier(0.25, 0.46, 0.45, 0.94),
    color            120ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

nav.toc a:hover {
  color: var(--color-text);
  background: var(--color-surface);
}

nav.toc small {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  opacity: 0.7;
  margin-left: 4px;
}

/* ── Main ───────────────────────────────────────────────────── */
main { max-width: 68ch; }

/* ── Day section ────────────────────────────────────────────── */
section + section { margin-top: 64px; }

section > h2 {
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  margin: 0 0 24px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border);
  user-select: none;
}

/* ── Article list §8.2 ──────────────────────────────────────── */
article + article {
  border-top: 1px solid var(--color-border);
  padding-top: 24px;
  margin-top: 24px;
}

article {
  transition:
    background-color 120ms cubic-bezier(0.25, 0.46, 0.45, 0.94),
    padding          120ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

article:hover {
  background-color: var(--color-surface);
  padding-inline: 12px;
  margin-inline: -12px;
  border-radius: 8px;
}

article > header { margin-bottom: 12px; }

article h3 {
  margin: 0 0 6px;
  font-size: var(--text-lg);
}

article h3 a { text-decoration: none; }
article h3 a:hover { color: var(--color-accent); }

/* Article meta row */
.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 0;
}

/* Badge §8.3 */
.badge {
  display: inline-flex;
  align-items: center;
  font-size: var(--text-xs);
  font-family: ui-monospace, 'Monaspace Neon', monospace;
  font-weight: 600;
  letter-spacing: 0.06em;
  border-radius: 4px;
  padding: 2px 6px;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  background: transparent;
  user-select: none;
}

/* Article body */
.article-body {
  font-size: var(--text-base);
  line-height: 1.7;
  color: var(--color-text);
}

.article-body > *:last-child { margin-bottom: 0; }

.article-body h1, .article-body h2, .article-body h3,
.article-body h4, .article-body h5 {
  font-weight: 600;
  color: var(--color-text);
  margin: 24px 0 8px;
}

.article-body code {
  font-family: ui-monospace, 'Monaspace Neon', monospace;
  font-size: 0.875em;
  background: var(--color-surface);
  border-radius: 4px;
  padding: 1px 5px;
}

.article-body pre {
  background: var(--color-surface);
  border-radius: 8px;
  padding: 16px;
  overflow-x: auto;
  font-size: 0.875rem;
  line-height: 1.6;
  margin: 16px 0;
}

.article-body pre code { background: none; padding: 0; }

.article-body blockquote {
  margin: 16px 0;
  padding-left: 16px;
  border-left: 2px solid var(--color-border);
  color: var(--color-text-muted);
  font-style: italic;
}

/* ── Footer ─────────────────────────────────────────────────── */
.site-footer {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 32px 48px;
  border-top: 1px solid var(--color-border);
}

.site-footer p {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.6;
}

/* ── Reduced motion §6.5 ────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration:   0.01ms !important;
    transition-duration:  0.01ms !important;
    scroll-behavior:      auto   !important;
  }
}

/* ── Mobile §10 ─────────────────────────────────────────────── */
@media (max-width: 768px) {
  .site-header { padding: 32px 16px 24px; }

  .layout {
    grid-template-columns: 1fr;
    padding: 24px 16px 64px;
    gap: 0;
  }

  nav.toc {
    position: static;
    max-height: none;
    overflow: visible;
    margin-bottom: 32px;
    padding-bottom: 24px;
    padding-right: 0;
    border-bottom: 1px solid var(--color-border);
  }

  nav.toc ol {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 4px;
  }

  h1 { font-size: var(--text-xl); }
}
"""


# ── DB helpers ───────────────────────────────────────────────────────────────

def all_items(conn: sqlite3.Connection):
    return conn.execute(
        """SELECT id, title, source_id, content, created_at, run_id
           FROM items ORDER BY run_id ASC, created_at ASC"""
    ).fetchall()


# ── Data helpers ─────────────────────────────────────────────────────────────

def day_key(run_id: str) -> str:
    return run_id[:8]   # "20240705"


def day_label(key: str) -> str:
    try:
        dt = datetime.strptime(key, "%Y%m%d")
        days = ["一", "二", "三", "四", "五", "六", "日"]
        return dt.strftime(f"%m月%d日 · 周{days[dt.weekday()]}")
    except Exception:
        return key


def day_anchor(key: str) -> str:
    return f"day-{key}"


def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return url


def week_range(day_keys) -> str:
    if not day_keys:
        return ""
    try:
        first = datetime.strptime(day_keys[0],  "%Y%m%d")
        last  = datetime.strptime(day_keys[-1], "%Y%m%d")
        return (f"{first.strftime('%Y年%m月%d日')}"
                f" — {last.strftime('%m月%d日')}")
    except Exception:
        return ""


def group_by_day(rows):
    days = defaultdict(list)
    for row in rows:
        days[day_key(row[5])].append(row)
    return sorted(days.items())


# ── HTML rendering ───────────────────────────────────────────────────────────

def render_article(item) -> str:
    _, title, source_id, content, created_at, run_id = item
    t   = html.escape(title or "(无标题)")
    src = html.escape(domain(source_id))
    url = html.escape(source_id)
    body = _md(content)

    return f"""<article>
  <header>
    <h3><a href="{url}">{t}</a></h3>
    <p class="meta">
      <span class="badge">{src}</span>
    </p>
  </header>
  <div class="article-body">{body}</div>
</article>"""


def render_sections(grouped) -> str:
    parts = []
    for key, items in grouped:
        anchor = day_anchor(key)
        label  = day_label(key)
        articles = "\n".join(render_article(i) for i in items)
        parts.append(f"""<section id="{anchor}">
  <h2>{label} &thinsp;·&thinsp; {len(items)} 篇</h2>
  {articles}
</section>""")
    return "\n\n".join(parts)


def render_toc(grouped) -> str:
    items_html = "\n".join(
        f'  <li><a href="#{day_anchor(k)}">'
        f'{day_label(k)}<small>{len(v)}</small></a></li>'
        for k, v in grouped
    )
    return f"""<nav class="toc" aria-label="目录">
  <p>目录</p>
  <ol>{items_html}</ol>
</nav>"""


def render_page(grouped, total: int, week: str) -> str:
    toc      = render_toc(grouped)
    sections = render_sections(grouped)
    now      = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>nodeu2c 周报 · {week}</title>
<style>{CSS}</style>
</head>
<body>

<header class="site-header">
  <p class="label">nodeu2c 周报</p>
  <h1>{week}</h1>
  <p class="meta">{total} 篇文章 · 生成于 {now}</p>
</header>

<div class="layout">
  {toc}
  <main>{sections}</main>
</div>

<footer class="site-footer">
  <p>nodeu2c 自动生成 · GitHub Actions · RSS 订阅聚合</p>
</footer>

</body>
</html>"""


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = all_items(conn)
    finally:
        conn.close()

    grouped = group_by_day(rows)
    day_keys = [k for k, _ in grouped]
    week     = week_range(day_keys)

    html_out = render_page(grouped, len(rows), week)
    OUT_HTML.write_text(html_out, encoding="utf-8")

    OUT_SUBJECT.write_text(
        f"周报 · {week} · {len(rows)} 篇文章"
    )
    print(f"render_weekly: {len(rows)} items, {len(grouped)} days → {OUT_HTML.name}")


if __name__ == "__main__":
    main()
