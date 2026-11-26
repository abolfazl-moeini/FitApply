"""Tests for Typer CLI commands."""

import tempfile
from pathlib import Path
from typer.testing import CliRunner
from fitapply.cli import app
from fitapply.store import JobStore

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "fitapply" in result.stdout
    assert "parse" in result.stdout
    assert "audit" in result.stdout
    assert "status" in result.stdout
    assert "run" in result.stdout


def test_cli_audit_missing_file():
    result = runner.invoke(app, ["audit", "--resume", "missing_cv.pdf"])
    assert result.exit_code == 1
    assert "Failed to audit resume" in result.stdout


def test_cli_status_export():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        out_report = Path(tmpdir) / "report.md"
        result = runner.invoke(app, ["status", "--db", str(db_path), "--export", str(out_report)])
        assert result.exit_code == 0
        assert out_report.exists()
        assert "Report successfully exported to" in result.stdout


def test_cli_status_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        result = runner.invoke(app, ["status", "--db", str(db_path)])
        assert result.exit_code == 0
        assert "Total Jobs Tracked" in result.stdout


def test_cli_run_missing_resume():
    result = runner.invoke(app, ["run", "--resume", "non_existent_file.pdf"])
    assert result.exit_code == 1
    assert "Resume file not found" in result.stdout


def test_cli_end_to_end_simulated_run():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "test_cv.pdf"
        import pymupdf
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((50, 72), "Ali Moeini - Python Developer")
        doc.save(str(pdf_path))
        doc.close()

        # Seed profile cache so LLM is not called over network
        cache_path = pdf_path.with_suffix(".pdf.profile.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write("""{
                "full_name": "Ali Moeini",
                "summary": "Experienced Python Engineer",
                "top_skills": ["Python", "FastAPI"],
                "secondary_skills": ["SQL"],
                "experiences": [],
                "education": [],
                "languages": ["Persian", "English"],
                "years_of_experience": 5.0
            }""")

        db_path = Path(tmpdir) / "jobs.db"

        # Run with non-existent site to test pipeline initialization without network calls
        result = runner.invoke(
            app,
            [
                "run",
                "--resume", str(pdf_path),
                "--sites", "unknown_site",
                "--dry-run",
                "--auto",
            ],
        )
        assert result.exit_code == 0
        assert "Candidate parsed from PDF: Ali Moeini" in result.stdout


def test_cli_run_without_pdf_using_config_profile():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_path = Path(tmpdir) / "config.yaml"
        cfg_path.write_text("""
candidate_profile:
  full_name: "Sara Rad"
  headline: "Python Developer"
  top_skills: ["Python", "FastAPI"]
  years_of_experience: 4
search:
  platforms: ["jobinja"]
  keywords: ["Python"]
matching:
  min_fit_score: 75
        """, encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "run",
                "--config", str(cfg_path),
                "--sites", "unknown_site",
                "--dry-run",
                "--auto",
            ],
        )
        assert result.exit_code == 0
        assert "Using site-hosted resume + config profile" in result.stdout
        assert "Sara Rad" in result.stdout


def test_cli_run_invalid_upload_mode():
    result = runner.invoke(
        app,
        ["run", "--upload-mode", "invalid_mode", "--sites", "unknown_site"],
    )
    assert result.exit_code == 1
    assert "Invalid upload mode" in result.stdout
