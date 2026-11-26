"""Tests for CandidateProfile and Resume models."""

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
