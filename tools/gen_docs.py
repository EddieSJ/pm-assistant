#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《项目需求说明书》的 .md 源稿重新生成为同风格 .html 交付物。

用法：
    python gen_docs.py <md路径> <html输出路径> <课程标签>
其中 <课程标签> 取 "课程1" 或 "课程2"（决定主题色）。
"""
import html
import re
import sys
from pathlib import Path

THEMES = {
    "课程1": dict(accent="#2563eb", soft="#eef4ff", badge_border="#d5e2fb",
                  bq_text="#33415c", pulse="37,99,235"),
    "课程2": dict(accent="#7c3aed", soft="#f3eefe", badge_border="#e0d2fb",
                  bq_text="#3f3a52", pulse="124,58,237"),
    "课程3": dict(accent="#0f7b6c", soft="#e6f5f1", badge_border="#c6e8e0",
                  bq_text="#2c4f49", pulse="15,123,108"),
}


def inline(text: str) -> str:
    s = html.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s


def cell(text: str) -> str:
    t = text.strip()
    body = inline(t)
    if t.startswith("✅"):
        return f'<span class="s-done">{body}</span>'
    if t.startswith("⬜") or t.startswith("🟡"):
        return f'<span class="s-todo">{body}</span>'
    return body


def is_sep(cells):
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def render_table(rows):
    if not rows:
        return ""
    out = ["  <table>"]
    header, *body = rows
    out.append("    <tr>" + "".join(f"<th>{inline(c)}</th>" for c in header) + "</tr>")
    for r in body:
        out.append("    <tr>" + "".join(f"<td>{cell(c)}</td>" for c in r) + "</tr>")
    out.append("  </table>")
    return "\n".join(out)


def render_quote(lines):
    out = ["  <blockquote>"]
    buf = []
    for ln in lines:
        if ln.startswith("- "):
            buf.append(ln[2:].strip())
        else:
            if buf:
                out.append("    <ul>" + "".join(f"<li>{inline(x)}</li>" for x in buf) + "</ul>")
                buf = []
            out.append(f"    <p>{inline(ln)}</p>")
    if buf:
        out.append("    <ul>" + "".join(f"<li>{inline(x)}</li>" for x in buf) + "</ul>")
    out.append("  </blockquote>")
    return "\n".join(out)


def render_body(lines):
    out = []
    i = 0
    n = len(lines)
    opened = False
    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        s = line.strip()
        if not s or s == "---":
            i += 1
            continue
        if s.startswith("## "):
            if opened:
                out.append("</section>")
                out.append("")
            opened = True
            m = re.match(r"##\s*(\d+)\.\s*(.*)", s)
            if m:
                num, title = m.group(1), m.group(2)
            else:
                num, title = "", re.sub(r"^##\s*", "", s)
            out.append(f'<section id="s{num or len(out)}">')
            out.append(f'  <h2><span class="n">{num}</span>{inline(title)}</h2>')
            i += 1
            continue
        if s.startswith("### "):
            out.append(f"  <h3>{inline(s[4:].strip())}</h3>")
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not is_sep(cells):
                    rows.append(cells)
                i += 1
            out.append(render_table(rows))
            continue
        if s.startswith(">"):
            q = []
            while i < n and lines[i].strip().startswith(">"):
                ct = lines[i].strip()[1:].strip()
                q.append(ct)
                i += 1
            out.append(render_quote(q))
            continue
        if s.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            out.append("  <ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        if re.match(r"^\d+\.\s", s):
            items = []
            while i < n and re.match(r"^\d+\.\s", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s*", "", lines[i].strip()))
                i += 1
            out.append("  <ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue
        out.append(f"  <p>{inline(s)}</p>")
        i += 1
    if opened:
        out.append("</section>")
    return "\n".join(out)


def build(md_text: str, label: str) -> str:
    t = THEMES[label]
    lines = md_text.splitlines()
    first_h2 = next((k for k, l in enumerate(lines) if l.strip().startswith("## ")), len(lines))
    preamble, body = lines[:first_h2], lines[first_h2:]

    title_line = next((l for l in preamble if l.strip().startswith("# ")), "# 文档")
    title = title_line.strip()[2:].strip()
    m = re.match(r"(.*?)（(.+?)）\s*$", title)
    base, subtitle = (m.group(1).strip(), m.group(2).strip()) if m else (title, "")

    def grab(key):
        for l in preamble:
            mm = re.search(key + r"：\s*(.+)$", l)
            if mm:
                return mm.group(1).strip()
        return ""

    version = grab("版本").split("｜")[0].strip()
    date = grab("更新时间").split("｜")[0].strip()
    courseware = re.sub(r"[`]", "", grab("对应课件")).split("｜")[0].split("|")[0].strip()
    summary = grab("交付摘要")
    lead = grab("概述")

    meta_lines = [l.strip()[1:].strip() for l in preamble if l.strip().startswith(">")]
    docinfo = [l for l in meta_lines
               if not re.search(r"(版本|更新时间|交付摘要|概述)：", l)]

    toc = []
    for l in body:
        if l.strip().startswith("## "):
            mm = re.match(r"##\s*(\d+)\.\s*(.*)", l.strip())
            num, tt = (mm.group(1), mm.group(2)) if mm else ("", re.sub(r"^##\s*", "", l.strip()))
            toc.append((num, tt))
    toc_html = "\n".join(
        f'    <li><a href="#s{num or k+1}">{num + ". " if num else ""}{inline(tt)}</a></li>'
        for k, (num, tt) in enumerate(toc))

    style = f""":root{{
  --bg:#f6f8fb; --card:#ffffff; --ink:#182235; --muted:#5b6779;
  --border:#e3e8f0; --accent:{t['accent']}; --accent-soft:{t['soft']};
  --done:#16a34a; --done-soft:#e9f9ef; --todo:#8a94a6; --todo-soft:#f1f3f7;
  --mono:"SF Mono",ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.75;font-size:15px}}
a{{color:var(--accent);text-decoration:none}}
a:hover{{text-decoration:underline}}
.wrap{{max-width:980px;margin:0 auto;padding:0 24px 80px}}
header{{padding:48px 0 28px;border-bottom:1px solid var(--border);margin-bottom:36px}}
.kicker{{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--accent);font-weight:600;letter-spacing:.4px}}
.dot{{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 0 rgba({t['pulse']},.5);animation:pulse 2s infinite}}
@keyframes pulse{{0%{{box-shadow:0 0 0 0 rgba({t['pulse']},.5)}}70%{{box-shadow:0 0 0 8px rgba({t['pulse']},0)}}100%{{box-shadow:0 0 0 0 rgba({t['pulse']},0)}}}}
h1{{font-size:30px;margin:10px 0 12px;line-height:1.3}}
.meta{{display:flex;flex-wrap:wrap;gap:8px}}
.badge{{font-size:12px;padding:3px 10px;border-radius:999px;background:var(--accent-soft);color:var(--accent);border:1px solid {t['badge_border']}}}
.badge.v{{background:#fff;color:var(--muted);border-color:var(--border)}}
.lead{{margin-top:16px;color:var(--muted);font-size:14.5px;max-width:860px}}
nav.toc{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px 22px;margin-bottom:32px}}
nav.toc h2{{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin:0 0 10px}}
nav.toc ol{{margin:0;padding-left:20px;columns:2;column-gap:32px}}
nav.toc li{{margin:4px 0;font-size:13.5px;break-inside:avoid}}
section{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:28px 32px;margin-bottom:26px}}
h2{{font-size:21px;margin:0 0 16px;padding-bottom:12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}}
h2 .n{{color:var(--accent);font-family:var(--mono);font-size:15px;background:var(--accent-soft);border-radius:6px;padding:2px 9px}}
h3{{font-size:16px;margin:24px 0 10px}}
p{{margin:8px 0}}
ul,ol{{margin:8px 0;padding-left:24px}}
li{{margin:4px 0}}
table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px}}
th{{background:var(--accent-soft);color:var(--ink);text-align:left;font-weight:600;padding:9px 12px;border:1px solid var(--border)}}
td{{padding:8px 12px;border:1px solid var(--border);vertical-align:top}}
tr:nth-child(even) td{{background:#fafbfd}}
td code{{background:#f1f3f7;padding:1px 6px;border-radius:4px;font-family:var(--mono);font-size:12.5px}}
.s-done{{display:inline-block;font-size:11.5px;font-weight:600;color:var(--done);background:var(--done-soft);border:1px solid #bfe8cf;padding:1px 8px;border-radius:999px;white-space:nowrap}}
.s-todo{{display:inline-block;font-size:11.5px;font-weight:600;color:var(--todo);background:var(--todo-soft);border:1px solid #dde2ea;padding:1px 8px;border-radius:999px;white-space:nowrap}}
code{{font-family:var(--mono);font-size:13px}}
blockquote{{border-left:3px solid var(--accent);background:var(--accent-soft);margin:14px 0;padding:10px 16px;border-radius:0 8px 8px 0;color:{t['bq_text']}}}
blockquote p{{margin:4px 0}}
footer{{margin-top:20px;color:var(--muted);font-size:12.5px;text-align:center;padding:20px}}
@media(max-width:720px){{nav.toc ol{{columns:1}}section{{padding:20px}}}}"""

    badges = [f'<span class="badge v">版本 {inline(version)}</span>',
              f'<span class="badge v">更新 {inline(date)}</span>']
    if summary:
        badges.append(f'<span class="badge">{inline(summary)}</span>')
    if courseware:
        badges.append(f'<span class="badge v">对应课件：{inline(courseware)}</span>')

    docinfo_html = render_quote(docinfo) if docinfo else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>项目管理智能助手 — 项目需求说明书（{label}）</title>
<style>
{style}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="kicker"><span class="dot"></span>项目需求说明书 · PRD</div>
  <h1>{inline(base)}<br><span style="font-size:22px;color:var(--accent)">{inline(subtitle)}</span></h1>
  <div class="meta">
    {"    ".join(badges)}
  </div>
  <p class="lead">{inline(lead)}</p>
</header>

{docinfo_html}

<nav class="toc">
  <h2>目录</h2>
  <ol>
{toc_html}
  </ol>
</nav>

{render_body(body)}

<footer>
  项目管理智能助手 · 项目需求说明书（{label}）{inline(version)} · 本文档为 .html 交付物，源稿见 项目需求说明书-{label}.md（唯一编辑入口）
</footer>

</div>
</body>
</html>
"""


def main():
    if len(sys.argv) < 4:
        print("usage: gen_docs.py <md> <html> <课程1|课程2>")
        sys.exit(2)
    md_path, html_path, label = sys.argv[1], sys.argv[2], sys.argv[3]
    text = Path(md_path).read_text(encoding="utf-8")
    out = build(text, label)
    Path(html_path).write_text(out, encoding="utf-8")
    print(f"OK: {html_path} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
