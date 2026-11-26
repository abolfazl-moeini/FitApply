"""Tests for reporting module (Markdown and HTML)."""

import tempfile
from pathlib import Path
from fitapply.report import export_report, generate_html_report, generate_markdown_report
from fitapply.store import JobStore
from fitapply.discovery.base import JobPosting


def test_markdown_and_html_generation():
    stats = {
        "total": 3,
        "applied_today": 1,
        "by_status": {"applied": 1, "dry_run": 1, "skipped": 1},
    }
    jobs = [
        {
            "id": "jobvision:101",
            "platform": "jobvision",
            "title": "Senior Python Engineer",
            "company": "Tech Corp",
            "url": "https://jobvision.ir/jobs/101",
            "location": "Tehran / Remote",
            "status": "applied",
            "fit_score": 92,
            "fit_reasons": "Perfect stack match",
            "missing_skills": '["Go"]',
            "cover_letter": "سلام، رزومه من برای این موقعیت ارسال می‌گردد.",
            "created_at": "2026-11-26 12:00:00",
        },
        {
            "id": "remotive:202",
            "platform": "remotive",
            "title": "Staff Backend Engineer",
            "company": "Global Remote Inc",
            "url": "https://remotive.com/jobs/202",
            "location": "Worldwide",
            "status": "dry_run",
            "fit_score": 78,
            "fit_reasons": "Strong background, meets requirements",
            "missing_skills": "[]",
            "cover_letter": "Hello, I am excited to apply for this role.",
            "created_at": "2026-11-26 14:00:00",
        },
    ]

    md = generate_markdown_report(stats, jobs)
    assert "# FitApply Job Application Report" in md
    assert "Senior Python Engineer" in md
    assert "Tech Corp" in md
    assert "92%" in md

    html_out = generate_html_report(stats, jobs)
    assert "<!DOCTYPE html>" in html_out
    assert "FitApply - Job Report Dashboard" in html_out
    assert "Global Remote Inc" in html_out
    assert "92% Match" in html_out


def test_export_report_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_report.db"
        store = JobStore(db_path)

        job = JobPosting(
            id="jobinja:555",
            platform="jobinja",
            title="FastAPI Developer",
            company="Startup",
            url="https://jobinja.ir/jobs/555",
            description="FastAPI role",
        )
        store.record_discovery(job)
        store.record_match_result(
            job_id=job.id,
            fit_score=85,
            fit_reasons="Good match",
            missing_skills=[],
            cover_letter="Cover note",
            status="applied",
        )

        md_file = Path(tmpdir) / "reports_nested" / "sub" / "report.md"
        out_md = export_report(db_path, output_path=md_file, open_browser=False)
        assert out_md.exists()
        assert "FastAPI Developer" in out_md.read_text(encoding="utf-8")

        html_file = Path(tmpdir) / "report.html"
        out_html = export_report(db_path, output_path=html_file, open_browser=False)
        assert out_html.exists()
        assert "<!DOCTYPE html>" in out_html.read_text(encoding="utf-8")


def test_report_sanitization_and_markdown_table_safety():
    stats = {"total": 1, "applied_today": 0, "by_status": {"applied": 1}}
    jobs = [
        {
            "id": "test:1",
            "platform": "jobinja",
            "title": "Dev | Lead\nSenior",
            "company": "Acme\r\nInc",
            "url": "javascript:alert(1)",
            "location": "Remote",
            "status": 'applied"><script>alert(1)</script>',
            "fit_score": 88,
            "fit_reasons": "Good",
            "missing_skills": "[]",
            "cover_letter": "",
            "created_at": "2026-11-26",
        }
    ]
    md = generate_markdown_report(stats, jobs)
    assert "| 88% | `applied\"><script>alert(1)</script>` | Dev - Lead Senior | Acme  Inc | jobinja | Remote |" in md

    html_out = generate_html_report(stats, jobs)
    assert "javascript:alert(1)" not in html_out
    assert "<script>alert(1)</script>" not in html_out
    assert 'href="#"' in html_out
