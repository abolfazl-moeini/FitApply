"""Tests for BrowserApplier rules, upload modes, and indicator safety."""

import pytest
from pathlib import Path
from fitapply.applier import (
    ALREADY_APPLIED_INDICATORS,
    POST_CLICK_SUCCESS_INDICATORS,
    SITE_PROFILE_DEFAULT_PLATFORMS,
    BrowserApplier,
    _host_matches,
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


def test_board_host_matching_respects_subdomain_boundaries():
    assert _host_matches("jobs.linkedin.com", {"linkedin.com"})
    assert not _host_matches("linkedin.com.evil.test", {"linkedin.com"})


@pytest.mark.asyncio
async def test_apply_rejects_foreign_posting_url_before_browser_io(monkeypatch):
    applier = BrowserApplier()
    async def forbidden_connect():
        raise AssertionError("browser must not connect for a foreign posting URL")
    monkeypatch.setattr(applier, "_get_or_connect_context", forbidden_connect)
    job = JobPosting(id="linkedin:1", platform="linkedin", title="Dev", company="Acme",
                     url="https://linkedin.com.evil.test/jobs/1", description="role")
    candidate = CandidateProfile(full_name="Ali", summary="Dev", top_skills=["Python"])
    evaluation = JobMatchEvaluation(fit_score=90, reasons="Match", is_good_match=True, cover_letter="Hi")
    result = await applier.apply_to_job(job, candidate, evaluation, object(), dry_run=True)  # type: ignore[arg-type]
    assert result["status"] == "manual_action"


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


@pytest.mark.asyncio
async def test_always_upload_requires_readable_pdf_before_browser_connect(monkeypatch):
    applier = BrowserApplier()
    connected = False

    async def connect():
        nonlocal connected
        connected = True
        raise AssertionError("browser must not be opened")

    monkeypatch.setattr(applier, "_get_or_connect_context", connect)
    job = JobPosting(id="linkedin:1", platform="linkedin", title="Dev", company="Co", url="https://linkedin.com/jobs/1", description="Python")
    candidate = CandidateProfile(full_name="Candidate", summary="Engineer", top_skills=["Python"], email="private@example.com")
    evaluation = JobMatchEvaluation(fit_score=90, reasons="Good", is_good_match=True, cover_letter="Hello")
    result = await applier.apply_to_job(job, candidate, evaluation, object(), resume_path=None, dry_run=False, upload_mode="always_upload")  # type: ignore[arg-type]
    assert result["status"] == "failed"
    assert "readable resume PDF" in result["error"]
    assert connected is False


@pytest.mark.asyncio
async def test_dynamic_answers_only_fill_snapshotted_fields_and_minimize_prompt():
    applier = BrowserApplier()

    class Locator:
        def __init__(self):
            self.value = ""
            self.fills = []

        async def is_visible(self, **kwargs): return True
        async def is_enabled(self): return True
        async def input_value(self): return self.value
        async def fill(self, value): self.value = value; self.fills.append(value)

    loc = Locator()

    class Page:
        async def evaluate(self, *args):
            return [{"key": "fitapply-0", "tag": "INPUT", "type": "text", "label": "Years of experience", "options": []}]
        def locator(self, selector):
            return loc if selector == '[data-fitapply-id="fitapply-0"]' else Locator()

    class FakeLLM:
        prompt = ""
        async def complete_structured(self, *, prompt, response_model, system):
            self.prompt = prompt
            return ScreeningAnswers(answers=[FieldAnswer(field_key="email", value="attacker@example.com"), FieldAnswer(field_key="fitapply-0", value="5")])

    from fitapply.applier import FieldAnswer, ScreeningAnswers
    candidate = CandidateProfile(full_name="Private Name", email="private@example.com", summary="Engineer", top_skills=["Python"])
    llm = FakeLLM()
    await applier._answer_dynamic_questions(Page(), candidate, {"email": "private@example.com", "military_status": "exempt"}, llm)  # type: ignore[arg-type]
    assert loc.fills == ["5"]
    assert "private@example.com" not in llm.prompt
    assert "Private Name" not in llm.prompt
    assert "military_status" not in llm.prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "upload_mode", "url"),
    [
        ("jobinja", "auto", "https://jobinja.ir/jobs/10"),
        ("jobinja", "always_upload", "https://jobinja.ir/jobs/10"),
        ("linkedin", "auto", "https://www.linkedin.com/jobs/view/10"),
        ("linkedin", "site_profile", "https://www.linkedin.com/jobs/view/10"),
    ],
)
async def test_dry_run_is_read_only_for_all_upload_modes(tmp_path, monkeypatch, platform, upload_mode, url):
    class FakePage:
        async def goto(self, *args, **kwargs):
            pass
        async def close(self):
            pass

    class FakeContext:
        async def new_page(self):
            return FakePage()

    applier = BrowserApplier()
    async def fake_connect():
        return FakeContext(), None
    monkeypatch.setattr(applier, "_get_or_connect_context", fake_connect)
    monkeypatch.setattr(applier, "_receipt_text", lambda page: _async_result(""))
    monkeypatch.setattr(applier, "_is_apply_button_present", lambda page: _async_result(True))

    mutation_calls = []
    async def mutation(*args, **kwargs):
        mutation_calls.append(1)
    for name in ("_click_apply_button", "_click_final_submit", "_fill_cover_letter", "_fill_screening_fields", "_answer_dynamic_questions", "_upload_resume_if_needed"):
        monkeypatch.setattr(applier, name, mutation)

    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"pdf")
    result = await applier.apply_to_job(
        JobPosting(id=f"{platform}:10", platform=platform, title="Dev", company="Acme", url=url, description="role"),
        CandidateProfile(full_name="Ali", summary="Dev", top_skills=["Python"]),
        JobMatchEvaluation(fit_score=90, reasons="fit", is_good_match=True, cover_letter="hello"),
        object(), candidate_extra={"salary": "123"}, resume_path=pdf, dry_run=True, upload_mode=upload_mode,  # type: ignore[arg-type]
    )
    assert result["status"] == "dry_run"
    assert mutation_calls == []


async def _async_result(value):
    return value


@pytest.mark.asyncio
async def test_dry_run_preserves_existing_receipt_and_missing_control(monkeypatch):
    class FakePage:
        async def goto(self, *args, **kwargs):
            pass
        async def close(self):
            pass

    class FakeContext:
        async def new_page(self):
            return FakePage()

    applier = BrowserApplier()
    async def fake_connect():
        return FakeContext(), None
    monkeypatch.setattr(applier, "_get_or_connect_context", fake_connect)
    job = JobPosting(id="linkedin:11", platform="linkedin", title="Dev", company="Acme", url="https://linkedin.com/jobs/view/11", description="role")
    candidate = CandidateProfile(full_name="Ali", summary="Dev", top_skills=["Python"])
    evaluation = JobMatchEvaluation(fit_score=90, reasons="fit", is_good_match=True, cover_letter="hello")

    monkeypatch.setattr(applier, "_receipt_text", lambda page: _async_result("Application submitted"))
    existing = await applier.apply_to_job(job, candidate, evaluation, object(), dry_run=True)  # type: ignore[arg-type]
    assert existing["status"] == "already_applied"

    monkeypatch.setattr(applier, "_receipt_text", lambda page: _async_result("ordinary job description"))
    monkeypatch.setattr(applier, "_is_apply_button_present", lambda page: _async_result(False))
    missing = await applier.apply_to_job(job, candidate, evaluation, object(), dry_run=True)  # type: ignore[arg-type]
    assert missing["status"] == "dry_run"
    assert "no form changes" in missing["notes"]
