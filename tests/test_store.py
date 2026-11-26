"""Tests for SQLite JobStore."""

import tempfile
from pathlib import Path
import pytest
from fitapply.discovery.base import JobPosting
from fitapply.store import JobStore


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_jobs.db"
        yield JobStore(db_path)


def test_store_discovery_and_deduplication(temp_store: JobStore):
    job = JobPosting(
        id="jobinja:12345",
        platform="jobinja",
        title="Python Backend Developer",
        company="Tech Co",
        url="https://jobinja.ir/jobs/12345",
        location="Tehran",
        description="Senior Python developer with FastAPI and PostgreSQL",
    )

    assert not temp_store.is_job_seen(job.id)

    temp_store.record_discovery(job)
    assert temp_store.is_job_seen(job.id)


def test_store_match_result_and_stats(temp_store: JobStore):
    job = JobPosting(
        id="jobvision:67890",
        platform="jobvision",
        title="Django Developer",
        company="Startup Co",
        url="https://jobvision.ir/jobs/67890",
        description="Django and React",
    )

    temp_store.record_discovery(job)
    temp_store.record_match_result(
        job_id=job.id,
        fit_score=85,
        fit_reasons="Strong Django experience",
        missing_skills=["Docker"],
        cover_letter="سلام، من علاقه‌مند به این موقعیت هستم.",
        status="skipped",
    )

    stats = temp_store.get_stats()
    assert stats["total"] == 1
    assert stats["by_status"].get("skipped") == 1

    temp_store.record_application(job.id, status="applied", notes="Applied via Playwright")
    stats_updated = temp_store.get_stats()
    assert stats_updated["applied_today"] == 1
    assert stats_updated["by_status"].get("applied") == 1
