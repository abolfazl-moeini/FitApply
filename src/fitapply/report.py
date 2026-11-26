"""Reporting generator module for FitApply (Markdown and Standalone HTML Dashboard)."""

from __future__ import annotations

import html
import json
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fitapply.store import JobStore


def generate_markdown_report(stats: Dict[str, Any], jobs: List[Dict[str, Any]]) -> str:
    """Generate a clean, structured Markdown report of applications and opportunities."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# FitApply Job Application Report 📊",
        f"*Generated on: {now_str}*",
        "",
        "## 1. Summary Statistics",
        f"- **Total Jobs Tracked:** {stats.get('total', 0)}",
        f"- **Applied Today:** {stats.get('applied_today', 0)}",
    ]

    by_status = stats.get("by_status", {})
    if by_status:
        lines.append("- **Status Breakdown:**")
        for st, count in by_status.items():
            lines.append(f"  - `{st}`: {count}")
    lines.append("")

    lines.append("## 2. Jobs Overview")
    if not jobs:
        lines.append("*No jobs found matching criteria.*")
        return "\n".join(lines)

    lines.append("| Score | Status | Title | Company | Platform | Location | Link |")
    lines.append("| :---: | :---: | :--- | :--- | :---: | :---: | :---: |")

    for j in jobs:
        score_val = f"{j['fit_score']}%" if j.get("fit_score") is not None else "-"
        status_val = f"`{j.get('status', 'discovered')}`"
        title = j.get("title", "").replace("|", "-")
        company = j.get("company", "").replace("|", "-")
        platform = j.get("platform", "")
        location = j.get("location") or "N/A"
        url = j.get("url", "#")
        lines.append(f"| {score_val} | {status_val} | {title} | {company} | {platform} | {location} | [Open Link]({url}) |")

    lines.append("")
    lines.append("## 3. High-Fit Opportunities Detail")
    high_fit = [j for j in jobs if (j.get("fit_score") or 0) >= 75]
    if not high_fit:
        lines.append("*No jobs with fit score >= 75% found in this batch.*")
    else:
        for idx, j in enumerate(high_fit, 1):
            lines.append(f"### {idx}. {j['title']} @ {j['company']}")
            lines.append(f"- **Platform:** {j['platform']} | **Status:** `{j['status']}` | **Score:** {j['fit_score']}%")
            lines.append(f"- **URL:** {j['url']}")
            if j.get("fit_reasons"):
                lines.append(f"- **Fit Reasons:** {j['fit_reasons']}")
            if j.get("missing_skills"):
                try:
                    missing = json.loads(j["missing_skills"])
                    if missing:
                        lines.append(f"- **Missing Skills:** {', '.join(missing)}")
                except Exception:
                    pass
            if j.get("cover_letter"):
                lines.append(f"- **Tailored Cover Note:**\n```text\n{j['cover_letter']}\n```")
            lines.append("")

    return "\n".join(lines)


def generate_html_report(stats: Dict[str, Any], jobs: List[Dict[str, Any]]) -> str:
    """Generate a sleek, self-contained single-page HTML report dashboard without external server dependencies."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    job_cards_html = []
    for j in jobs:
        score = j.get("fit_score")
        score_badge = (
            f'<span class="score high">{score}% Match</span>'
            if score and score >= 80
            else (
                f'<span class="score medium">{score}% Match</span>'
                if score and score >= 70
                else (f'<span class="score low">{score}%</span>' if score is not None else '<span class="score none">No Score</span>')
            )
        )

        status_class = j.get("status", "discovered")
        status_badge = f'<span class="badge {status_class}">{status_class}</span>'

        missing_skills_list = ""
        if j.get("missing_skills"):
            try:
                ms = json.loads(j["missing_skills"])
                if ms:
                    missing_skills_list = '<div class="missing-skills"><strong>Missing:</strong> ' + ", ".join(
                        f'<span class="skill-tag">{html.escape(s)}</span>' for s in ms
                    ) + '</div>'
            except Exception:
                pass

        reasons = html.escape(j.get("fit_reasons") or "No detailed reasoning recorded.")
        cover = html.escape(j.get("cover_letter") or "")
        cover_section = f'<details class="cover-toggle"><summary>View Tailored Pitch / Cover Note</summary><pre>{cover}</pre></details>' if cover else ""

        card = f"""
        <div class="card {status_class}">
            <div class="card-header">
                <div>
                    <h3 class="job-title">{html.escape(j.get('title', 'Unknown Job'))}</h3>
                    <div class="company-name">{html.escape(j.get('company', 'Unknown Company'))} &bull; <span class="platform-tag">{html.escape(j.get('platform', ''))}</span> &bull; <span class="loc">{html.escape(j.get('location') or 'Remote / Unspecified')}</span></div>
                </div>
                <div class="badges">
                    {score_badge}
                    {status_badge}
                </div>
            </div>
            <div class="card-body">
                <p class="reasons">{reasons}</p>
                {missing_skills_list}
                {cover_section}
            </div>
            <div class="card-footer">
                <a href="{html.escape(j.get('url', '#'))}" target="_blank" rel="noopener noreferrer" class="btn-link">View Job Posting &rarr;</a>
                <span class="date">{html.escape(j.get('created_at', ''))[:10]}</span>
            </div>
        </div>
        """
        job_cards_html.append(card)

    cards_joined = "\n".join(job_cards_html) if job_cards_html else '<p class="empty-state">No jobs found matching criteria.</p>'

    by_status_items = "".join(
        f'<div class="stat-pill"><span class="pill-label">{html.escape(st)}:</span> <span class="pill-val">{cnt}</span></div>'
        for st, cnt in stats.get("by_status", {}).items()
    )

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FitApply - Job Report Dashboard</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --font: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text-main);
            font-family: var(--font);
            line-height: 1.5;
            padding: 2rem 1rem;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        header {{
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--surface-border);
            padding-bottom: 1.5rem;
            flex-wrap: wrap;
            gap: 1rem;
        }}
        h1 {{ font-size: 1.75rem; font-weight: 700; color: var(--text-main); }}
        h1 span {{ color: var(--primary); }}
        .timestamp {{ color: var(--text-muted); font-size: 0.875rem; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: 12px;
            padding: 1.25rem;
        }}
        .stat-val {{ font-size: 2rem; font-weight: 700; color: var(--primary); }}
        .stat-label {{ font-size: 0.875rem; color: var(--text-muted); }}
        .status-pills {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
        .stat-pill {{
            background: #0f172a;
            border: 1px solid var(--surface-border);
            padding: 0.25rem 0.5rem;
            border-radius: 6px;
            font-size: 0.75rem;
        }}
        .pill-label {{ color: var(--text-muted); }}
        .pill-val {{ font-weight: bold; color: var(--text-main); }}
        .card-list {{ display: flex; flex-direction: column; gap: 1rem; }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: 12px;
            padding: 1.25rem;
            transition: transform 0.15s ease, border-color 0.15s ease;
        }}
        .card:hover {{ border-color: var(--primary); transform: translateY(-2px); }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 0.75rem;
        }}
        .job-title {{ font-size: 1.2rem; font-weight: 600; color: var(--text-main); }}
        .company-name {{ color: var(--text-muted); font-size: 0.875rem; margin-top: 0.25rem; }}
        .platform-tag {{
            background: #334155;
            color: #e2e8f0;
            padding: 0.1rem 0.4rem;
            border-radius: 4px;
            font-size: 0.75rem;
            text-transform: uppercase;
        }}
        .badges {{ display: flex; gap: 0.5rem; align-items: center; }}
        .score {{
            font-size: 0.85rem;
            font-weight: 700;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
        }}
        .score.high {{ background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }}
        .score.medium {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }}
        .score.low {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }}
        .score.none {{ background: #334155; color: #94a3b8; }}
        .badge {{
            font-size: 0.75rem;
            text-transform: uppercase;
            padding: 0.2rem 0.5rem;
            border-radius: 6px;
            font-weight: 600;
        }}
        .badge.applied {{ background: #15803d; color: #fff; }}
        .badge.dry_run {{ background: #b45309; color: #fff; }}
        .badge.skipped {{ background: #475569; color: #cbd5e1; }}
        .badge.failed {{ background: #b91c1c; color: #fff; }}
        .reasons {{ font-size: 0.925rem; color: #e2e8f0; margin-bottom: 0.75rem; }}
        .missing-skills {{ font-size: 0.85rem; color: #f87171; margin-bottom: 0.75rem; }}
        .skill-tag {{
            background: rgba(239, 68, 68, 0.15);
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            margin-right: 0.3rem;
        }}
        details.cover-toggle {{
            background: #0f172a;
            border: 1px solid var(--surface-border);
            border-radius: 8px;
            padding: 0.6rem;
            font-size: 0.85rem;
            margin-top: 0.5rem;
        }}
        details.cover-toggle summary {{ cursor: pointer; color: var(--primary); font-weight: 500; }}
        details.cover-toggle pre {{
            margin-top: 0.5rem;
            white-space: pre-wrap;
            font-family: inherit;
            color: #cbd5e1;
            font-size: 0.85rem;
        }}
        .card-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 1rem;
            padding-top: 0.75rem;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }}
        .btn-link {{
            color: var(--primary);
            text-decoration: none;
            font-size: 0.875rem;
            font-weight: 600;
        }}
        .btn-link:hover {{ text-decoration: underline; }}
        .date {{ font-size: 0.75rem; color: var(--text-muted); }}
        .empty-state {{ text-align: center; color: var(--text-muted); padding: 3rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>Fit<span>Apply</span> Dashboard</h1>
                <div class="timestamp">Generated: {now_str}</div>
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-val">{stats.get('total', 0)}</div>
                <div class="stat-label">Total Jobs Evaluated</div>
            </div>
            <div class="stat-card">
                <div class="stat-val" style="color: var(--success);">{stats.get('applied_today', 0)}</div>
                <div class="stat-label">Applied Today</div>
            </div>
            <div class="stat-card">
                <div class="stat-label" style="margin-bottom: 0.25rem;">Status Breakdown</div>
                <div class="status-pills">
                    {by_status_items}
                </div>
            </div>
        </div>

        <h2 style="font-size: 1.25rem; margin-bottom: 1rem;">Opportunities & Applications</h2>
        <div class="card-list">
            {cards_joined}
        </div>
    </div>
</body>
</html>
"""
    return html_template


def export_report(
    db_path: Path | str,
    output_path: Optional[Path | str] = None,
    min_score: Optional[int] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    open_browser: bool = False,
) -> Path:
    """Query JobStore and export to either Markdown or HTML report."""
    store = JobStore(db_path)
    stats = store.get_stats()
    jobs = store.get_recent_jobs(
        limit=limit,
        min_score=min_score,
        status_filter=status_filter,
        sort_by="fit_score",
    )

    out_file = Path(output_path) if output_path else Path("report.html" if open_browser else "report.md")

    if out_file.suffix.lower() == ".html":
        content = generate_html_report(stats, jobs)
    else:
        content = generate_markdown_report(stats, jobs)

    out_file.write_text(content, encoding="utf-8")

    if open_browser and out_file.suffix.lower() == ".html":
        webbrowser.open(f"file://{out_file.resolve()}")

    return out_file
