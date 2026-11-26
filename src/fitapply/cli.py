"""Typer command-line interface for Job Apply Agent."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

load_dotenv()

from fitapply.applier import BrowserApplier
from fitapply.discovery import get_discoverers_for_platforms
from fitapply.discovery.base import JobPosting
from fitapply.llm import get_llm_provider
from fitapply.matcher import evaluate_job_fit
from fitapply.report import export_report
from fitapply.resume import audit_resume, parse_resume_to_profile
from fitapply.store import JobStore

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("fitapply")

app = typer.Typer(
    name="fitapply",
    help="AI-powered autonomous job application agent for Iranian and global job boards.",
    no_args_is_help=True,
)
console = Console()


def load_config(config_path: Optional[Path]) -> Dict[str, Any]:
    """Load configuration from YAML file or fallback to example."""
    candidates = [
        config_path,
        Path("config.yaml"),
        Path("config.example.yaml"),
    ]
    for p in candidates:
        if p and p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


@app.command()
def parse(
    resume: Path = typer.Option(Path("resume.pdf"), "--resume", "-r", help="Path to resume PDF file"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
):
    """Test extracting structured candidate profile from resume PDF."""

    async def _run():
        cfg = load_config(config)
        llm = get_llm_provider(cfg)
        console.print(f"[bold cyan]Reading resume from:[/bold cyan] {resume}")

        try:
            profile = await parse_resume_to_profile(resume, llm)
            console.print(Panel(
                f"[bold green]Name:[/bold green] {profile.full_name}\n"
                f"[bold green]Experience:[/bold green] {profile.years_of_experience} years\n"
                f"[bold green]Top Skills:[/bold green] {', '.join(profile.top_skills)}\n"
                f"[bold green]Summary:[/bold green] {profile.summary}",
                title="Candidate Profile Extracted Successfully",
            ))
        except Exception as e:
            console.print(f"[bold red]Failed to parse resume:[/bold red] {e}")
            raise typer.Exit(1)

    asyncio.run(_run())


@app.command()
def audit(
    resume: Path = typer.Option(Path("resume.pdf"), "--resume", "-r", help="Path to resume PDF file"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
):
    """Perform a brutally honest ATS diagnostic audit on your resume PDF."""

    async def _run():
        cfg = load_config(config)
        llm = get_llm_provider(cfg)
        console.print(f"[bold cyan]🔍 Auditing resume for ATS compatibility:[/bold cyan] {resume}")

        try:
            result = await audit_resume(resume, llm)
            score_color = "green" if result.ats_score >= 80 else ("yellow" if result.ats_score >= 60 else "red")

            console.print(Panel(
                f"[bold {score_color}]ATS Score: {result.ats_score} / 100[/bold {score_color}]\n\n"
                f"[bold]Verdict:[/bold] {result.summary_verdict}\n\n"
                f"[bold green]Keywords Detected:[/bold] {', '.join(result.detected_keywords) or 'None'}\n"
                f"[bold red]Missing Industry Keywords:[/bold] {', '.join(result.missing_critical_keywords) or 'None'}",
                title="🎯 ATS Diagnostic Score",
                border_style=score_color,
            ))

            if result.critical_issues:
                issues_text = "\n".join(f"• [red]{issue}[/red]" for issue in result.critical_issues)
                console.print(Panel(issues_text, title="⚠️ Critical Problems Found", border_style="red"))

            if result.actionable_fixes:
                fixes_text = "\n".join(f"✔ [green]{fix}[/green]" for fix in result.actionable_fixes)
                console.print(Panel(fixes_text, title="💡 Actionable Improvements", border_style="green"))

        except Exception as e:
            console.print(f"[bold red]Failed to audit resume:[/bold red] {e}")
            raise typer.Exit(1)

    asyncio.run(_run())


@app.command()
def status(
    db: Path = typer.Option(Path("data/jobs.db"), "--db", help="Path to SQLite database"),
    top: int = typer.Option(15, "--top", "-n", help="Number of jobs to list"),
    min_score: Optional[int] = typer.Option(None, "--min-score", help="Filter jobs with fit_score >= min_score"),
    status_filter: Optional[str] = typer.Option(None, "--status", help="Filter by status (applied, dry_run, skipped, failed)"),
    sort: str = typer.Option("fit_score", "--sort", help="Sort order: 'fit_score' or 'created_at'"),
    export: Optional[Path] = typer.Option(None, "--export", "-e", help="Export report to Markdown or HTML file (e.g. report.md / report.html)"),
    html: bool = typer.Option(False, "--html", help="Generate and instantly open standalone HTML dashboard in browser"),
):
    """Show job application history, filter opportunities, or export reports."""
    store = JobStore(db)
    stats = store.get_stats()

    console.print("\n[bold cyan]📊 FitApply Statistics & Applications[/bold cyan]")
    table = Table(title="Overview", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Total Jobs Tracked", str(stats["total"]))
    table.add_row("Applied Today", f"[green]{stats['applied_today']}[/green]")
    for status_name, count in stats.get("by_status", {}).items():
        table.add_row(f"Status: {status_name}", str(count))
    console.print(table)

    recent = store.get_recent_jobs(
        limit=top,
        min_score=min_score,
        status_filter=status_filter,
        sort_by=sort,
    )
    if recent:
        title_suffix = f" (Top {len(recent)})" if top else ""
        rec_table = Table(title=f"\nTracked Jobs{title_suffix}", show_header=True, header_style="bold blue")
        rec_table.add_column("Platform")
        rec_table.add_column("Title")
        rec_table.add_column("Company")
        rec_table.add_column("Score", justify="center")
        rec_table.add_column("Status", justify="center")

        for r in recent:
            score_str = f"{r['fit_score']}%" if r["fit_score"] is not None else "-"
            status_color = "green" if r["status"] == "applied" else ("yellow" if r["status"] == "dry_run" else "white")
            rec_table.add_row(
                r["platform"],
                r["title"][:30],
                r["company"][:20],
                score_str,
                f"[{status_color}]{r['status']}[/{status_color}]",
            )
        console.print(rec_table)

    if export or html:
        out_target = export or Path("report.html")
        created = export_report(
            db_path=db,
            output_path=out_target,
            min_score=min_score,
            status_filter=status_filter,
            limit=top,
            open_browser=html,
        )
        console.print(f"\n[bold green]✔ Report successfully exported to:[/bold green] {created}")


@app.command()
def run(
    resume: Optional[Path] = typer.Option(None, "--resume", "-r", help="Path to resume PDF file"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to config.yaml"),
    sites: Optional[str] = typer.Option(
        None,
        "--sites",
        "-s",
        help="Comma-separated sites: jobinja,jobvision,irantalent,remotive,themuse,linkedin,indeed",
    ),
    auto: bool = typer.Option(False, "--auto", help="Fully automated mode without interactive confirmation per job"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate form filling without clicking final submit button"),
    min_score: Optional[int] = typer.Option(None, "--min-score", help="Override minimum fit score threshold (0-100)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max jobs to apply in this run"),
    cdp_url: Optional[str] = typer.Option(None, "--cdp-url", help="Chrome DevTools Protocol URL"),
):
    """Discover jobs, score compatibility against resume, and apply."""

    async def _run():
        cfg = load_config(config)

        # Resume path resolution
        pdf_path = resume if resume is not None else Path(cfg.get("resume_path", "resume.pdf"))
        if not pdf_path.exists():
            console.print(
                f"[bold red]Resume file not found at:[/bold red] {pdf_path}\n"
                "Please provide a valid PDF via `--resume path/to/cv.pdf` or in `config.yaml`."
            )
            raise typer.Exit(1)

        # Platform resolution
        if sites:
            target_platforms = [s.strip() for s in sites.split(",") if s.strip()]
        else:
            target_platforms = cfg.get("search", {}).get("platforms", ["jobinja", "jobvision"])

        # Thresholds
        threshold = min_score if min_score is not None else cfg.get("matching", {}).get("min_fit_score", 75)
        max_apply = limit if limit is not None else cfg.get("matching", {}).get("max_applications_per_run", 10)
        keywords = cfg.get("search", {}).get("keywords", ["Backend Developer", "Python"])
        locations = cfg.get("search", {}).get("locations", ["Tehran", "Remote"])
        chrome_cdp = cdp_url if cdp_url is not None else cfg.get("chrome", {}).get("cdp_url", "http://localhost:9222")
        chrome_timeout = cfg.get("chrome", {}).get("timeout_seconds", 45)
        candidate_extra = cfg.get("candidate_answers", {})

        console.print(Panel(
            f"[bold]Resume:[/bold] {pdf_path}\n"
            f"[bold]Platforms:[/bold] {', '.join(target_platforms)}\n"
            f"[bold]Keywords:[/bold] {', '.join(keywords)}\n"
            f"[bold]Min Score:[/bold] {threshold}% | [bold]Max Applications:[/bold] {max_apply}\n"
            f"[bold]Mode:[/bold] {'Dry-Run (Simulate)' if dry_run else ('Full Auto' if auto else 'Interactive (Confirm per job)')}\n"
            f"[bold]Chrome CDP:[/bold] {chrome_cdp}",
            title="🚀 Starting Job Apply Agent",
            border_style="cyan",
        ))

        llm = get_llm_provider(cfg)
        store = JobStore(Path(cfg.get("db_path", "data/jobs.db")))
        applier = BrowserApplier(cdp_url=chrome_cdp, timeout_seconds=chrome_timeout)

        # 1. Parse Resume
        with console.status("[bold green]Parsing resume PDF..."):
            try:
                candidate = await parse_resume_to_profile(pdf_path, llm)
            except Exception as e:
                console.print(f"[bold red]Failed to parse resume:[/bold red] {e}")
                raise typer.Exit(1)
        console.print(f"👤 Candidate parsed: [bold green]{candidate.full_name}[/bold green] ({candidate.years_of_experience} yrs exp)")

        # 2. Discover Jobs
        from fitapply.discovery import DISCOVERERS

        unknown_platforms = [p for p in target_platforms if p.lower().strip() not in DISCOVERERS]
        if unknown_platforms:
            console.print(f"[yellow]Warning: Unrecognized platform(s) ignored: {', '.join(unknown_platforms)}[/yellow]")

        discoverers = get_discoverers_for_platforms(target_platforms)
        all_jobs: List[JobPosting] = []
        seen_in_run: set[str] = set()

        for disc in discoverers:
            with console.status(f"[bold yellow]Searching {disc.platform_name}..."):
                jobs = await disc.search_jobs(keywords=keywords, locations=locations, limit=max_apply * 2)
                unique_jobs = [j for j in jobs if j.id not in seen_in_run and not seen_in_run.add(j.id)]
                console.print(f"Found [bold]{len(unique_jobs)}[/bold] job postings on {disc.platform_name}")
                all_jobs.extend(unique_jobs)

        if not all_jobs:
            console.print("[yellow]No job postings found matching search criteria.[/yellow]")
            return

        applied_count = 0
        evaluated_count = 0
        skipped_count = 0
        failed_count = 0

        # 3. Evaluate and Apply
        for job in all_jobs:
            if applied_count >= max_apply:
                console.print(f"[bold green]Reached maximum applications limit ({max_apply}) for this run.[/bold green]")
                break

            if store.is_job_seen(job.id):
                continue

            store.record_discovery(job)

            with console.status(f"[bold cyan]Evaluating fit for: {job.title} @ {job.company}..."):
                evaluation = await evaluate_job_fit(
                    candidate=candidate,
                    job=job,
                    llm=llm,
                    min_score=threshold,
                    candidate_extra=candidate_extra,
                )
            evaluated_count += 1

            # Display Evaluation Card
            score_color = "green" if evaluation.fit_score >= 80 else ("yellow" if evaluation.fit_score >= threshold else "red")
            console.print(Panel(
                f"[bold]Company:[/bold] {job.company} | [bold]Platform:[/bold] {job.platform}\n"
                f"[bold]URL:[/bold] {job.url}\n"
                f"[bold]Fit Score:[/bold] [{score_color}]{evaluation.fit_score}%[/{score_color}] "
                f"({'Match' if evaluation.is_good_match else 'Below Threshold'}) | "
                f"[bold]Seniority:[/bold] {evaluation.seniority_fit or 'N/A'} | "
                f"[bold]Comp:[/bold] {evaluation.compensation_fit or 'N/A'}\n"
                f"[bold]Reasons:[/bold] {evaluation.reasons}\n"
                f"[bold]Missing Skills:[/bold] {', '.join(evaluation.missing_skills) if evaluation.missing_skills else 'None'}\n"
                f"[bold]Cover Note:[/bold]\n{evaluation.cover_letter}",
                title=f"Job Analysis: {job.title}",
                border_style=score_color,
            ))

            if not evaluation.is_good_match or (not auto and not Confirm.ask(
                f"Send application to [bold cyan]{job.company}[/bold cyan] ({evaluation.fit_score}%)?",
                default=True,
            )):
                skipped_count += 1
                store.record_match_result(
                    job_id=job.id,
                    fit_score=evaluation.fit_score,
                    fit_reasons=evaluation.reasons,
                    missing_skills=evaluation.missing_skills,
                    cover_letter=evaluation.cover_letter,
                    status="skipped",
                )
                continue

            # Execute browser application
            with console.status(f"[bold magenta]Applying via browser (dry_run={dry_run})..."):
                app_res = await applier.apply_to_job(
                    job=job,
                    candidate=candidate,
                    evaluation=evaluation,
                    llm=llm,
                    candidate_extra=candidate_extra,
                    resume_path=pdf_path,
                    dry_run=dry_run,
                )

            final_status = app_res["status"] if app_res.get("success") else "failed"
            store.record_match_result(
                job_id=job.id,
                fit_score=evaluation.fit_score,
                fit_reasons=evaluation.reasons,
                missing_skills=evaluation.missing_skills,
                cover_letter=evaluation.cover_letter,
                status=final_status,
            )
            store.record_application(
                job.id,
                status=final_status,
                notes=app_res.get("notes") if app_res.get("success") else app_res.get("error"),
            )

            if app_res.get("success"):
                if final_status in ("applied", "dry_run"):
                    applied_count += 1
                console.print(f"[bold green]✔ {final_status}:[/bold green] {app_res.get('notes', 'Done')}")
            else:
                failed_count += 1
                console.print(f"[bold red]✘ Failed:[/bold red] {app_res.get('error')}")

            # Polite delay between browser actions
            await asyncio.sleep(3)

        console.print(Panel(
            f"[bold green]✔ Run Completed![/bold green]\n"
            f"- Discovered: [bold]{len(all_jobs)}[/bold] | Evaluated: [bold]{evaluated_count}[/bold]\n"
            f"- Applied/Simulated: [bold green]{applied_count}[/bold green] | Skipped: [yellow]{skipped_count}[/yellow] | Failed: [red]{failed_count}[/red]\n"
            f"- View detailed visual dashboard: [cyan]uv run fitapply status --html[/cyan]\n"
            f"- Export comprehensive report: [cyan]uv run fitapply status --export report.md[/cyan]",
            title="🏁 Execution Summary",
            border_style="green",
        ))

    asyncio.run(_run())


if __name__ == "__main__":
    app()
