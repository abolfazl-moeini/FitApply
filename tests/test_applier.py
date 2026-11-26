"""Tests for BrowserApplier rules, upload modes, and indicator safety."""

import pytest
from pathlib import Path
from fitapply.applier import (
    ALREADY_APPLIED_INDICATORS,
    POST_CLICK_SUCCESS_INDICATORS,
    SITE_PROFILE_DEFAULT_PLATFORMS,
    BrowserApplier,
)
from fitapply.discovery.base import JobPosting
from fitapply.matcher import JobMatchEvaluation
from fitapply.resume import CandidateProfile


def test_already_applied_indicators_safe_from_general_english():
    sample_job_body = "We are seeking a Senior ML Engineer with experience in Applied Machine Learning and NLP."
    for ind in ALREADY_APPLIED_INDICATORS:
        assert ind not in sample_job_body


def test_site_profile_default_platforms():
    assert "jobinja" in SITE_PROFILE_DEFAULT_PLATFORMS
    assert "jobvision" in SITE_PROFILE_DEFAULT_PLATFORMS
    assert "irantalent" in SITE_PROFILE_DEFAULT_PLATFORMS


def test_post_click_success_indicators_present():
    assert any("موفقیت" in ind for ind in POST_CLICK_SUCCESS_INDICATORS)
    assert any("Application submitted" in ind for ind in POST_CLICK_SUCCESS_INDICATORS)


@pytest.mark.asyncio
async def test_site_profile_mode_skips_pdf_upload_and_safe_dry_run(tmp_path, monkeypatch):
    """Ensure Iranian boards in auto/site_profile mode never touch file inputs or click 1-click submit in dry-run."""
    dummy_pdf = tmp_path / "cv.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy")

    class FakePage:
        async def goto(self, *args, **kwargs):
            pass

        async def inner_text(self, selector):
            return "آگهی استخدام برنامه‌نویس پایتون"

        async def close(self):
            pass

    class FakeContext:
        async def new_page(self):
            return FakePage()

    applier = BrowserApplier()

    async def fake_connect():
        return FakeContext(), None

    upload_called = False
    apply_clicked = False

    async def fake_upload(*args, **kwargs):
        nonlocal upload_called
        upload_called = True

    async def fake_click_apply(*args, **kwargs):
        nonlocal apply_clicked
        apply_clicked = True
        return True

    async def fake_is_apply_present(*args, **kwargs):
        return True

    async def fake_fill_cover(*args, **kwargs):
        pass

    monkeypatch.setattr(applier, "_get_or_connect_context", fake_connect)
    monkeypatch.setattr(applier, "_upload_resume_if_needed", fake_upload)
    monkeypatch.setattr(applier, "_click_apply_button", fake_click_apply)
    monkeypatch.setattr(applier, "_is_apply_button_present", fake_is_apply_present)
    monkeypatch.setattr(applier, "_fill_cover_letter", fake_fill_cover)

    job = JobPosting(
        id="jobinja:1",
        platform="jobinja",
        title="Python Dev",
        company="TestCo",
        url="https://jobinja.ir/jobs/1",
        description="Python",
    )
    candidate = CandidateProfile(full_name="Ali", summary="Dev", top_skills=["Python"])
    evaluation = JobMatchEvaluation(
        fit_score=90,
        reasons="Match",
        is_good_match=True,
        cover_letter="سلام",
    )

    class NoopLLM:
        pass

    res = await applier.apply_to_job(
        job=job,
        candidate=candidate,
        evaluation=evaluation,
        llm=NoopLLM(),  # type: ignore[arg-type]
        resume_path=dummy_pdf,
        dry_run=True,
        upload_mode="auto",
    )

    assert res["success"] is True
    assert res["status"] == "dry_run"
    assert upload_called is False
    assert apply_clicked is False
