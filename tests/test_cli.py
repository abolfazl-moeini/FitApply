"""Tests for Typer CLI commands."""

import tempfile
from pathlib import Path
from typer.testing import CliRunner
from fitapply import cli
from fitapply.cli import app
from fitapply.store import JobStore
from fitapply.discovery.base import JobPosting

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


def test_cli_rejects_unknown_site_before_startup():
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
        from fitapply.resume import _pdf_fingerprint
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write("""{
                "full_name": "Ali Moeini",
                "summary": "Experienced Python Engineer",
                "top_skills": ["Python", "FastAPI"],
                "secondary_skills": ["SQL"],
                "experiences": [],
                "education": [],
                "languages": ["Persian", "English"],
                "years_of_experience": 5.0,
                "_source_sha256": """ + __import__("json").dumps(_pdf_fingerprint(pdf_path)) + """
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
        assert result.exit_code == 1
        assert "recognized platform" in result.stdout


def test_cli_rejects_unknown_site_from_config():
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
        assert result.exit_code == 1
        assert "recognized platform" in result.stdout


def test_cli_run_invalid_upload_mode():
    result = runner.invoke(
        app,
        ["run", "--upload-mode", "invalid_mode", "--sites", "jobinja"],
    )
    assert result.exit_code == 1
    assert "Invalid upload mode" in result.stdout


def test_cli_run_hermetic_successful_workflow(tmp_path, monkeypatch):
    """Exercise normal CLI orchestration with injected fakes and only temp files."""
    cfg = tmp_path / "config.yaml"
    db_path = tmp_path / "jobs.db"
    monkeypatch.chdir(tmp_path)
    cfg.write_text(
        "candidate_profile:\n"
        "  full_name: Sara Rad\n"
        "  headline: Python Developer\n"
        "  top_skills: [Python, FastAPI]\n"
        "search:\n"
        "  platforms: [jobinja]\n"
        "  keywords: [Python]\n"
        "  locations: [Remote]\n"
        "matching:\n"
        "  min_fit_score: 60\n"
        "  max_applications_per_run: 1\n"
        f"db_path: '{db_path}'\n",
        encoding="utf-8",
    )
    job = JobPosting(
        id="jobinja:fixture-1", platform="jobinja", title="Python Engineer", company="Acme",
        url="https://jobinja.ir/jobs/fixture-1", location="Remote", description="Python role",
    )
    calls = {"discoverer": 0, "provider": 0, "applier": 0}

    class FakeDiscoverer:
        platform_name = "jobinja"

        async def search_jobs(self, **kwargs):
            calls["discoverer"] += 1
            assert kwargs["keywords"] == ["Python"]
            return [job]

    class FakeProvider:
        async def complete(self, prompt, system=None):
            raise AssertionError("structured provider path expected")

        async def complete_structured(self, prompt, response_model, system=None):
            calls["provider"] += 1
            assert "Python" in prompt
            return response_model.model_validate({
                "fit_score": 90, "reasons": "Strong match", "missing_skills": [],
                "is_good_match": True, "cover_letter": "Hello", "seniority_fit": "well_matched",
                "compensation_fit": "unspecified",
            })

    class FakeApplier:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def apply_to_job(self, **kwargs):
            calls["applier"] += 1
            assert kwargs["dry_run"] is True
            return {"success": True, "status": "dry_run", "notes": "Fixture preview"}

    monkeypatch.setattr(cli, "get_llm_provider", lambda _cfg: FakeProvider())
    monkeypatch.setattr(cli, "get_discoverers_for_platforms", lambda _sites: [FakeDiscoverer()])
    monkeypatch.setattr(cli, "BrowserApplier", FakeApplier)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(cli.asyncio, "sleep", no_sleep)
    result = runner.invoke(app, ["run", "--config", str(cfg), "--dry-run", "--auto"])
    assert result.exit_code == 0, result.stdout
    assert calls == {"discoverer": 1, "provider": 1, "applier": 1}
    rows = JobStore(db_path).get_recent_jobs(limit=5)
    assert len(rows) == 1
    assert rows[0]["status"] == "dry_run"
    assert rows[0]["notes"] == "Fixture preview"


def test_run_rejects_missing_and_malformed_config_before_startup(tmp_path):
    missing = runner.invoke(app, ["run", "--config", str(tmp_path / "absent.yaml")])
    assert missing.exit_code == 1
    assert "Configuration error" in missing.stdout

    malformed = tmp_path / "bad.yaml"
    malformed.write_text("- scalar-root\n", encoding="utf-8")
    result = runner.invoke(app, ["run", "--config", str(malformed)])
    assert result.exit_code == 1
    assert "must be a mapping" in result.stdout


def test_run_rejects_unknown_platform_and_malformed_lists(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text('search:\n  platforms: ["not-a-board"]\n', encoding="utf-8")
    result = runner.invoke(app, ["run", "--config", str(config)])
    assert result.exit_code == 1
    assert "recognized platform" in result.stdout

    config.write_text('search:\n  platforms: jobinja\n', encoding="utf-8")
    result = runner.invoke(app, ["run", "--config", str(config)])
    assert result.exit_code == 1
    assert "list of strings" in result.stdout


def test_cli_status_uses_config_db_path_and_preserves_db_precedence(tmp_path):
    config_file = tmp_path / "config.yaml"
    db_relative = "custom_jobs.db"
    db_path = tmp_path / db_relative
    store = JobStore(db_path)
    job = JobPosting(
        id="jobinja:status-test",
        platform="jobinja",
        title="Custom DB Engineer",
        company="Custom Co",
        url="https://jobinja.ir/jobs/status-test",
        description="Role in custom db",
    )
    store.record_discovery(job)
    store.record_match_result(
        job_id=job.id,
        fit_score=95,
        fit_reasons="Great",
        missing_skills=[],
        cover_letter="Hi",
        status="applied",
    )

    config_file.write_text(f"db_path: '{db_relative}'\n", encoding="utf-8")

    # 1. status with --config resolves relative db_path to config.parent
    result = runner.invoke(app, ["status", "--config", str(config_file)])
    assert result.exit_code == 0
    assert "Custom Co" in result.stdout
    assert "Custom DB Engineer" in result.stdout

    # 2. explicit --db takes precedence over --config
    other_db = tmp_path / "other.db"
    JobStore(other_db)
    result_override = runner.invoke(app, ["status", "--config", str(config_file), "--db", str(other_db)])
    assert result_override.exit_code == 0
    assert "Custom Co" not in result_override.stdout
    assert "Total Jobs Tracked" in result_override.stdout


def test_cli_status_rejects_html_with_non_html_export(tmp_path):
    db_path = tmp_path / "jobs.db"
    JobStore(db_path)
    report_file = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["status", "--db", str(db_path), "--html", "--export", str(report_file)],
    )
    assert result.exit_code == 1
    assert "Report export failed" in result.stdout
    assert "Cannot open browser for a non-HTML export file" in result.stdout
