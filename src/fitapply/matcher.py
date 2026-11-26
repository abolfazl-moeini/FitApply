"""Job Matching and Fit Scoring engine using LLM."""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from pydantic import BaseModel, Field

from fitapply.discovery.base import JobPosting
from fitapply.llm import BaseLLM
from fitapply.resume import CandidateProfile

logger = logging.getLogger(__name__)


class JobMatchEvaluation(BaseModel):
    """Structured evaluation of a candidate's fit for a specific job."""

    fit_score: int = Field(description="Score from 0 to 100 representing how well candidate fits the job requirements")
    reasons: str = Field(description="Brief explanation of strengths, matching experience and suitability")
    missing_skills: List[str] = Field(default_factory=list, description="Skills or requirements the candidate lacks")
    is_good_match: bool = Field(description="True if fit_score is acceptable for applying")
    cover_letter: str = Field(
        description="A tailored, professional, concise cover note for the employer in the same language as the job ad (Persian or English)"
    )


async def evaluate_job_fit(
    candidate: CandidateProfile,
    job: JobPosting,
    llm: BaseLLM,
    min_score: int = 75,
    candidate_extra: Dict[str, Any] | None = None,
) -> JobMatchEvaluation:
    """Evaluate candidate profile against a job posting and generate customized cover letter."""
    extra_info_str = ""
    if candidate_extra:
        extra_info_str = "\nADDITIONAL CANDIDATE DETAILS:\n" + "\n".join(
            f"- {k}: {v}" for k, v in candidate_extra.items() if v
        )

    prompt = f"""You are an elite career advisor and technical recruiter.
Compare the following Candidate Profile with the Job Posting.
Evaluate how well the candidate matches the requirements, identify missing skills, and calculate a realistic fit score (0 to 100).

CRITERIA:
- 85-100: Excellent match; candidate possesses all core requirements and relevant experience.
- 70-84: Good match; candidate has most key skills and can quickly learn minor missing items.
- Below 70: Poor match or junior/senior mismatch.

Also generate a concise, compelling cover note / message for the employer (1-2 short paragraphs).
If the job posting is in Persian, write the cover letter in natural, polite Persian (احترام‌آمیز، بدون تکلف بیهوده).
If the job posting is in English, write the cover letter in fluent English.

---
CANDIDATE PROFILE:
Name: {candidate.full_name}
Summary: {candidate.summary}
Years of Experience: {candidate.years_of_experience}
Top Skills: {', '.join(candidate.top_skills)}
Secondary Skills: {', '.join(candidate.secondary_skills)}
Experiences:
{chr(10).join(f"- {exp.title} at {exp.company}: {', '.join(exp.highlights)}" for exp in candidate.experiences[:4])}
{extra_info_str}

---
JOB POSTING:
Platform: {job.platform}
Title: {job.title}
Company: {job.company}
Location: {job.location or 'Not specified'}
Job Description:
{job.description[:3000]}
---
"""

    eval_result = await llm.complete_structured(
        prompt=prompt,
        response_model=JobMatchEvaluation,
        system="Evaluate candidate job fit accurately and generate tailored cover letter in JSON format.",
    )

    eval_result.is_good_match = eval_result.fit_score >= min_score
    return eval_result
