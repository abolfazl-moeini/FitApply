"""Tests for CandidateProfile and Resume models."""

import pytest
from fitapply.resume import CandidateProfile, Education, WorkExperience


def test_candidate_profile_schema():
    profile = CandidateProfile(
        full_name="علی معینی",
        headline="Senior Backend Engineer",
        summary="توسعه‌دهنده با بیش از ۶ سال سابقه کار با پایتون و ابزارهای اتوماسیون",
        top_skills=["Python", "FastAPI", "PostgreSQL", "Docker"],
        secondary_skills=["Redis", "Playwright", "Git"],
        experiences=[
            WorkExperience(
                title="Senior Backend Developer",
                company="شرکت دانش‌بنیان",
                duration="2021 - Present",
                highlights=["طراحی معماری میکروسرویس", "بهینه‌سازی دیتابیس"],
            )
        ],
        education=[
            Education(
                degree="کارشناسی",
                field_of_study="مهندسی نرم‌افزار",
                institution="دانشگاه تهران",
            )
        ],
        languages=["Persian (Native)", "English (Fluent)"],
        years_of_experience=6.5,
    )

    assert profile.full_name == "علی معینی"
    assert len(profile.top_skills) == 4
    assert profile.years_of_experience == 6.5
    dumped = profile.model_dump()
    assert dumped["top_skills"][0] == "Python"


def test_build_profile_from_config():
    from fitapply.resume import build_profile_from_config

    cfg = {
        "candidate_profile": {
            "full_name": "Reza Rahimi",
            "headline": "Lead Python Architect",
            "years_of_experience": 8,
            "top_skills": ["Python", "FastAPI", "AsyncIO"],
            "summary": "Architect with 8 years of experience.",
        },
        "search": {
            "keywords": ["Python", "Backend"],
            "locations": ["Tehran"],
        },
    }

    profile = build_profile_from_config(cfg)
    assert profile.full_name == "Reza Rahimi"
    assert profile.headline == "Lead Python Architect"
    assert profile.years_of_experience == 8.0
    assert "FastAPI" in profile.top_skills
    assert profile.location == "Tehran"


def test_build_profile_from_config_empty_locations_and_zero_years():
    from fitapply.resume import build_profile_from_config

    cfg = {
        "candidate_profile": {
            "full_name": "Junior Dev",
            "years_of_experience": 0,
        },
        "search": {
            "keywords": ["Python"],
            "locations": [],
        },
    }
    profile = build_profile_from_config(cfg)
    assert profile.location == "Remote"
    assert profile.years_of_experience == 0.0


@pytest.mark.asyncio
async def test_parse_resume_cache_mtime_invalidation():
    import os
    import tempfile
    import time
    from pathlib import Path
    import pymupdf
    from fitapply.llm import BaseLLM
    from fitapply.resume import parse_resume_to_profile

    class CountingLLM(BaseLLM):
        def __init__(self):
            self.calls = 0

        async def complete(self, prompt: str, system: str | None = None) -> str:
            self.calls += 1
            return '{"full_name": "Updated Name", "summary": "New summary", "top_skills": ["Python"], "years_of_experience": 4.0}'

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "cv.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 72), "Sample CV")
        doc.save(str(pdf_path))
        doc.close()

        cache_path = pdf_path.with_suffix(".pdf.profile.json")
        cache_path.write_text('{"full_name": "Stale Cached Name", "summary": "Old", "top_skills": ["Python"], "years_of_experience": 1.0}', encoding="utf-8")

        # Make cache older than PDF
        now = time.time()
        os.utime(cache_path, (now - 100, now - 100))
        os.utime(pdf_path, (now, now))

        llm = CountingLLM()
        profile = await parse_resume_to_profile(pdf_path, llm=llm, use_cache=True)
        assert llm.calls == 1
        assert profile.full_name == "Updated Name"
