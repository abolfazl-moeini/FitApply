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


def test_preview_has_no_application_timestamp_and_can_be_claimed(temp_store: JobStore):
    job = JobPosting(id="x:1", platform="x", title="Dev", company="Co", url="https://x.test/1", description="Dev")
    temp_store.record_discovery(job)
    temp_store.record_application(job.id, "dry_run", "preview")
    row = temp_store.get_recent_jobs()[0]
    assert row["applied_at"] is None
    assert temp_store.claim_application(job.id)
    assert not temp_store.claim_application(job.id)
    temp_store.record_application(job.id, "applied", "confirmed")
    row = temp_store.get_recent_jobs()[0]
    assert row["status"] == "applied" and row["applied_at"] is not None
    assert not temp_store.claim_application(job.id)


def test_claim_is_atomic_across_independent_store_connections(temp_store: JobStore):
    job = JobPosting(id="x:2", platform="x", title="Dev", company="Co", url="https://x.test/2", description="Dev")
    temp_store.record_discovery(job)
    second = JobStore(temp_store.db_path)
    outcomes = [temp_store.claim_application(job.id), second.claim_application(job.id)]
    assert outcomes.count(True) == 1


def test_legacy_failed_requires_reconciliation_and_only_pre_submit_failure_retries(temp_store: JobStore):
    job = JobPosting(id="x:3", platform="x", title="Dev", company="Co", url="https://x.test/3", description="Dev")
    temp_store.record_discovery(job)
    temp_store.record_application(job.id, "failed", "old failure")
    assert not temp_store.claim_application(job.id)

    retry = JobPosting(id="x:3b", platform="x", title="Dev", company="Co", url="https://x.test/3b", description="Dev")
    temp_store.record_discovery(retry)
    assert temp_store.claim_application(retry.id)
    temp_store.record_application(retry.id, "failed", "[pre_submit] browser unavailable")
    assert temp_store.claim_application(retry.id)


def test_unclassified_failure_is_protected_as_unknown(temp_store: JobStore):
    job = JobPosting(id="x:4", platform="x", title="Dev", company="Co", url="https://x.test/4", description="Dev")
    temp_store.record_discovery(job)
    temp_store.record_application(job.id, "failed", "click timeout")
    row = temp_store.get_recent_jobs()[0]
    assert row["status"] == "submission_unknown"
    assert row["applied_at"] is None
    assert not temp_store.claim_application(job.id)
