"""Resume parser module using PyMuPDF and LLM extraction."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from fitapply.llm import BaseLLM

logger = logging.getLogger(__name__)


class WorkExperience(BaseModel):
    title: str = Field(description="Job title or role")
    company: str = Field(description="Company or organization name")
    duration: Optional[str] = Field(default=None, description="Dates or duration of work")
    highlights: List[str] = Field(default_factory=list, description="Key achievements or responsibilities")


class Education(BaseModel):
    degree: str = Field(description="Degree or certification")
    field_of_study: Optional[str] = Field(default=None, description="Field of study / major")
    institution: Optional[str] = Field(default=None, description="University or school")


class CandidateProfile(BaseModel):
    """Structured representation of a candidate parsed from their CV/resume."""

    full_name: str
    headline: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: str = Field(description="Professional bio / summary in Persian and/or English")
    top_skills: List[str] = Field(default_factory=list, description="Primary technical and domain skills")
    secondary_skills: List[str] = Field(default_factory=list, description="Secondary or supporting skills")
    experiences: List[WorkExperience] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    years_of_experience: float = Field(default=0.0)


def extract_text_from_pdf(pdf_path: Path | str) -> str:
    """Extract plain text from all pages of a PDF document using PyMuPDF."""
    import pymupdf

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume PDF file not found at: {path}")

    doc = pymupdf.open(str(path))
    texts: List[str] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        texts.append(page.get_text("text"))

    full_text = "\n".join(texts).strip()
    if not full_text:
        raise ValueError(f"No extractable text found in PDF: {path}. Check if it is a scanned image.")
    return full_text


async def parse_resume_to_profile(
    pdf_path: Path | str,
    llm: BaseLLM,
    use_cache: bool = True,
) -> CandidateProfile:
    """Parse resume PDF to CandidateProfile, caching result to avoid redundant token spend."""
    path = Path(pdf_path)
    cache_path = path.with_suffix(".pdf.profile.json")

    if use_cache and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Loaded candidate profile from cache: %s", cache_path)
            return CandidateProfile.model_validate(data)
        except Exception as e:
            logger.warning("Failed to load cached profile (%s), re-parsing.", e)

    raw_text = extract_text_from_pdf(path)

    prompt = f"""You are an expert HR and recruitment AI analyzer.
Analyze the following resume text carefully and extract a comprehensive, structured candidate profile.
The resume might be in Persian, English, or bilingual.
Extract all skills, work experiences, education, and calculate total years of experience.

RESUME CONTENT:
---
{raw_text}
---
"""

    profile = await llm.complete_structured(
        prompt=prompt,
        response_model=CandidateProfile,
        system="You extract candidate profiles from resumes into strict JSON schema.",
    )

    if use_cache:
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)
            logger.info("Saved candidate profile to cache: %s", cache_path)
        except Exception as e:
            logger.warning("Failed to save cache (%s)", e)

    return profile
