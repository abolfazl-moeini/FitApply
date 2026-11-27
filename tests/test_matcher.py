"""Tests for JobMatcher and evaluation models."""

import pytest
from fitapply.discovery.base import JobPosting
from fitapply.llm import BaseLLM
from fitapply.matcher import JobMatchEvaluation, evaluate_job_fit
from fitapply.resume import CandidateProfile


class MockLLM(BaseLLM):
    """Mock LLM returning deterministic evaluation."""

    async def complete(self, prompt: str, system: str | None = None) -> str:
        self.prompt = prompt
        return """{
            "fit_score": 88,
            "reasons": "مهارت‌های پایتون و لینوکس کاملاً با نیازمندی‌های آگهی همخوانی دارند.",
            "missing_skills": ["Kubernetes"],
            "is_good_match": true,
            "cover_letter": "با سلام، رزومه اینجانب با تخصص در پایتون ارسال می‌گردد."
        }"""


@pytest.mark.asyncio
async def test_evaluate_job_fit():
    candidate = CandidateProfile(
        full_name="Ali Moeini",
        summary="Python expert",
        top_skills=["Python", "PostgreSQL"],
        years_of_experience=5.0,
    )

    job = JobPosting(
        id="jobinja:101",
        platform="jobinja",
        title="Python Developer",
        company="Sample Tech",
        url="https://jobinja.ir/jobs/101",
        description="We need a Python developer with PostgreSQL skills",
    )

    llm = MockLLM()
    result = await evaluate_job_fit(candidate, job, llm, min_score=75)

    assert isinstance(result, JobMatchEvaluation)
    assert result.fit_score == 88
    assert result.is_good_match is True
    assert "Kubernetes" in result.missing_skills
    assert "با سلام" in result.cover_letter


@pytest.mark.asyncio
async def test_match_prompt_includes_salary_units_and_excludes_unneeded_personal_data():
    candidate = CandidateProfile(
        full_name="Ali Contact Marker", summary="Python engineer", top_skills=["Python"],
        years_of_experience=5,
    )
    job = JobPosting(
        id="remote:2", platform="remotive", title="Python Engineer", company="Acme",
        url="https://remotive.com/jobs/2", description="Python role", salary="$100k-$120k USD / year",
    )
    llm = MockLLM()
    await evaluate_job_fit(
        candidate, job, llm,
        candidate_extra={
            "salary_expectation_irr_monthly": 600000000,
            "email": "private-email-marker", "phone": "private-phone-marker",
            "military_service": "private-service-marker",
        },
        location_preferences=["Tehran", "Remote"],
    )
    assert "$100k-$120k USD / year" in llm.prompt
    assert "600000000 Iranian rials per month" in llm.prompt
    assert "Tehran, Remote" in llm.prompt
    assert "private-email-marker" not in llm.prompt
    assert "private-phone-marker" not in llm.prompt
    assert "private-service-marker" not in llm.prompt
    assert "Ali Contact Marker" not in llm.prompt
