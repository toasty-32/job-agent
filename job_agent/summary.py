"""The daily summary page: a self-contained HTML file that opens in the browser."""
from __future__ import annotations

import shutil
from datetime import date
from html import escape
from pathlib import Path

STYLE = """
:root { color-scheme: light dark; --bg:#f7f7f5; --card:#fff; --text:#1d1d1b; --muted:#6b6b66;
  --line:#e4e4df; --strong:#1f7a4d; --possible:#b26b00; --accent:#2457c5; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --card:#21211f; --text:#ececea;
  --muted:#a3a39e; --line:#34342f; --strong:#5cc28f; --possible:#e3a34a; --accent:#7da2ff; } }
body { margin:0; background:var(--bg); color:var(--text);
  font:15px/1.5 "Segoe UI", system-ui, sans-serif; }
main { max-width:860px; margin:0 auto; padding:32px 16px 64px; }
h1 { font-size:24px; margin:0 0 4px; }
.lede { color:var(--muted); margin:0 0 24px; }
.next { background:var(--card); border:1px solid var(--line); border-left:4px solid var(--accent);
  border-radius:8px; padding:12px 16px; margin-bottom:24px; }
.job { background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:16px 20px; margin-bottom:16px; }
.top { display:flex; gap:16px; align-items:baseline; justify-content:space-between; flex-wrap:wrap; }
.job h2 { font-size:18px; margin:0; }
.job h2 a { color:inherit; }
.meta { color:var(--muted); margin:2px 0 10px; }
.score { font-weight:700; font-variant-numeric:tabular-nums; white-space:nowrap; }
.strong { color:var(--strong); } .possible { color:var(--possible); }
.cols { display:grid; grid-template-columns:1fr 1fr; gap:4px 24px; }
@media (max-width:600px) { .cols { grid-template-columns:1fr; } }
h3 { font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin:10px 0 2px; }
ul { margin:0; padding-left:18px; }
code { font-size:13px; color:var(--muted); }
"""


def _items(values: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(v)}</li>" for v in values) + "</ul>" if values else "<p>None noted.</p>"


def _card(job_id: str, record: dict) -> str:
    job, score = record["job"], record["score"]
    verdict = score["verdict"]
    return f"""
<article class="job">
  <div class="top">
    <h2><a href="{escape(job['url'], quote=True)}">{escape(job['title'])}</a></h2>
    <span class="score {escape(verdict)}">{score['score']}/100 · {escape(verdict)}</span>
  </div>
  <p class="meta">{escape(job['company'])} · {escape(job['location'] or 'Location not listed')}
    {('· posted ' + escape(job['posted'])) if job.get('posted') else ''} · <code>{escape(job_id)}</code></p>
  <p>{escape(score['summary'])}</p>
  <div class="cols">
    <div><h3>Why it fits</h3>{_items(score['matching_strengths'])}</div>
    <div><h3>Gaps</h3>{_items(score['gaps'] + score['dealbreakers'])}</div>
  </div>
</article>"""


def render_summary(new: list[tuple[str, dict]], waiting: int, min_score: int, day: str) -> str:
    if new:
        lede = f"{len(new)} new job{'s' if len(new) != 1 else ''} scored {min_score} or higher today."
    else:
        lede = f"No new jobs scored {min_score} or higher today."
    if waiting:
        lede += f" {waiting} earlier suggestion{'s are' if waiting != 1 else ' is'} still waiting for your decision."
    body = "".join(_card(jid, r) for jid, r in new)
    next_step = (
        '<div class="next"><strong>Next:</strong> double-click <strong>Review jobs</strong> on your desktop. '
        "For each job, choose apply / skip / later and add a note. The agent then writes the CV and cover letter "
        "for every job you approve, and learns from your reasons.</div>"
        if new or waiting else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job matches {escape(day)}</title><style>{STYLE}</style></head>
<body><main>
<h1>Job matches · {escape(day)}</h1>
<p class="lede">{escape(lede)}</p>
{next_step}
{body}
</main></body></html>
"""


def write_summary(output_dir: Path, new: list[tuple[str, dict]], waiting: int, min_score: int) -> Path:
    day = date.today().isoformat()
    folder = output_dir / "summaries"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{day}.html"
    path.write_text(render_summary(new, waiting, min_score, day), encoding="utf-8")
    shutil.copyfile(path, output_dir / "latest-summary.html")
    return path


def write_error_page(output_dir: Path, error: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "latest-summary.html"
    path.write_text(
        f"<!doctype html><meta charset='utf-8'><title>Job agent error</title><style>{STYLE}</style>"
        f"<main><h1>Today's job search failed</h1><p class='lede'>Details are in the log folder "
        f"(output/logs). Paste the error below to Claude for help.</p><pre>{escape(error)}</pre></main>",
        encoding="utf-8",
    )
    return path
