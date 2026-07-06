from pathlib import Path
import sqlite3
import html
from datetime import datetime, UTC
from urllib.parse import urlparse
from collections import defaultdict

ROOT        = Path(__file__).resolve().parent.parent
DB_PATH     = ROOT / "current.db"
OUT_HTML    = ROOT / "daily_email.html"
OUT_SUBJECT = ROOT / "daily_subject.txt"

# ── Design-system colors ──────────────────────────────────────────────────────
BG         = "#f9f9fb"
SURFACE    = "#f2f2f6"
BORDER     = "#dddde9"
MUTED      = "#888898"
TEXT       = "#2c2c3a"
ACCENT     = "#3b5bdb"
ACCENT_DIM = "#eef1ff"

FONT = ("'OPPO Sans','PingFang SC','Microsoft YaHei',"
        "'Switzer','Open Sans',ui-sans-serif,system-ui,sans-serif")
MONO = "ui-monospace,'Monaspace Neon','Cascadia Code',monospace"


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_latest_run(conn: sqlite3.Connection):
    row = conn.execute(
        "SELECT run_id FROM items ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def get_items(conn: sqlite3.Connection, run_id: str):
    # 同时取 category，按 category / created_at 排序
    return conn.execute(
        """SELECT title, source_id, content, created_at, category
           FROM items WHERE run_id = ?
           ORDER BY category, created_at DESC""",
        (run_id,),
    ).fetchall()


# ── Helpers ───────────────────────────────────────────────────────────────────

def domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return url


def preview(text: str, max_chars: int = 900) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    return flat[:max_chars].rsplit(" ", 1)[0] + "…"


def fmt_date(run_id: str) -> str:
    try:
        dt   = datetime.strptime(run_id, "%Y%m%dT%H%M%SZ")
        days = ["一", "二", "三", "四", "五", "六", "日"]
        return dt.strftime(f"%Y年%m月%d日 · 周{days[dt.weekday()]}")
    except Exception:
        return run_id


# ── Rendering ─────────────────────────────────────────────────────────────────

def render_article(title, source_id, content, created_at, first_in_section: bool) -> str:
    sep = (f"border-top:1px solid {BORDER};"
           f"padding-top:24px;margin-top:24px;") if not first_in_section else ""
    t   = html.escape(title or "(无标题)")
    src = html.escape(domain(source_id))
    pre = html.escape(preview(content))
    url = html.escape(source_id)

    return f"""
<article style="display:block;{sep}">
  <p style="margin:0 0 5px;font-size:11px;font-weight:600;
            letter-spacing:.08em;text-transform:uppercase;
            color:{MUTED};font-family:{MONO}">{src}</p>
  <h2 style="margin:0 0 10px;font-size:20px;font-weight:600;
             line-height:1.3;letter-spacing:-.01em;color:{TEXT}">
    <a href="{url}" style="color:inherit;text-decoration:none">{t}</a>
  </h2>
  <p style="margin:0 0 10px;font-size:15px;line-height:1.7;
            color:{TEXT};letter-spacing:.015em">{pre}</p>
  <a href="{url}" style="font-size:13px;color:{ACCENT};
     text-decoration:none;letter-spacing:.01em">阅读全文 ↗</a>
</article>"""


def render_articles(items) -> str:
    if not items:
        return (f'<p style="color:{MUTED};text-align:center;'
                f'padding:48px 0;font-size:15px;">今日暂无新文章</p>')

    # 按 category 分组
    groups: dict[str, list] = defaultdict(list)
    for row in items:
        cat = row[4] or "其他"
        groups[cat].append(row)

    parts = []

    for cat_i, (cat, cat_items) in enumerate(sorted(groups.items())):
        # 分类标题（首个分类不加顶部间距）
        cat_top = "margin-top:48px;" if cat_i > 0 else ""
        parts.append(
            f'<div style="{cat_top}margin-bottom:28px;">'
            f'<p style="margin:0 0 16px;font-size:11px;font-weight:600;'
            f'letter-spacing:.10em;text-transform:uppercase;color:{MUTED};'
            f'border-bottom:1px solid {BORDER};padding-bottom:10px;">'
            f'{html.escape(cat)}</p>'
        )

        for j, (title, source_id, content, created_at, _) in enumerate(cat_items):
            parts.append(render_article(title, source_id, content, created_at, first_in_section=(j == 0)))

        parts.append('</div>')

    return "\n".join(parts)


def render_email(items, run_id: str) -> str:
    date_str = fmt_date(run_id) if run_id else "—"
    articles = render_articles(items)
    count    = len(items)

    return f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
</head>
<body style="margin:0;padding:0;background:{BG};
             font-family:{FONT};color:{TEXT};
             -webkit-text-size-adjust:100%">

<div style="max-width:660px;margin:0 auto;padding:40px 24px 64px">

  <!-- ── Header ─────────────────────────────────────── -->
  <header style="padding-bottom:24px;margin-bottom:40px;
                 border-bottom:1px solid {BORDER}">
    <p style="margin:0 0 8px;font-size:11px;font-weight:600;
              letter-spacing:.10em;text-transform:uppercase;
              color:{MUTED}">Daily Digest · nodeu2c</p>
    <h1 style="margin:0 0 10px;font-size:34px;font-weight:600;
               letter-spacing:-.03em;line-height:1.1;
               color:{TEXT}">{date_str}</h1>
    <p style="margin:0;font-size:14px;color:{MUTED};
              line-height:1.5">{count} 篇新文章收录</p>
  </header>

  <!-- ── Articles ───────────────────────────────────── -->
  <main>{articles}</main>

  <!-- ── Footer ─────────────────────────────────────── -->
  <footer style="margin-top:48px;padding-top:24px;
                 border-top:1px solid {BORDER}">
    <p style="margin:0;font-size:12px;color:{MUTED};line-height:1.6">
      由 <strong style="color:{TEXT};font-weight:600">nodeu2c</strong>
      自动生成 · GitHub Actions · RSS 订阅聚合
    </p>
  </footer>

</div>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        run_id = get_latest_run(conn)
        items  = get_items(conn, run_id) if run_id else []
    finally:
        conn.close()

    html_out = render_email(items, run_id)
    OUT_HTML.write_text(html_out, encoding="utf-8")

    date_str = fmt_date(run_id) if run_id else "—"
    OUT_SUBJECT.write_text(f"每日摘要 · {date_str} · {len(items)} 篇")

    print(f"render_daily: {len(items)} items → {OUT_HTML.name}")


if __name__ == "__main__":
    main()
