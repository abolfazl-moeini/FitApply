"""Integration tests for PDF generation, text extraction and profile caching."""

import tempfile
from pathlib import Path
import pymupdf
import pytest
from fitapply.llm import BaseLLM
from fitapply.resume import extract_text_from_pdf, parse_resume_to_profile


class MockProfileLLM(BaseLLM):
    async def complete(self, prompt: str, system: str | None = None) -> str:
        return """{
            "full_name": "توسعه‌دهنده پایتون",
            "summary": "توسعه‌دهنده نرم‌افزار با سابقه کار در سیستم‌های بک‌اند",
            "top_skills": ["Python", "FastAPI", "Docker"],
            "secondary_skills": ["Git", "SQL"],
            "experiences": [],
            "education": [],
            "languages": ["Persian", "English"],
            "years_of_experience": 4.0
        }"""


def create_sample_pdf(pdf_path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Ali Moeini - Senior Backend Engineer\nSkills: Python, FastAPI, Docker")
    doc.save(str(pdf_path))
    doc.close()


@pytest.mark.asyncio
async def test_pdf_extraction_and_caching():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "test_cv.pdf"
        create_sample_pdf(pdf_path)

        text = extract_text_from_pdf(pdf_path)
        assert "Ali Moeini" in text
        assert "Python" in text

        llm = MockProfileLLM()
        profile1 = await parse_resume_to_profile(pdf_path, llm, use_cache=True)
        assert profile1.full_name == "توسعه‌دهنده پایتون"
        assert profile1.years_of_experience == 4.0

        cache_file = pdf_path.with_suffix(".pdf.profile.json")
        assert cache_file.exists()

        # Second read uses cache without calling complete()
        class FailingLLM(BaseLLM):
            async def complete(self, prompt: str, system: str | None = None) -> str:
                raise RuntimeError("Should not be called because cache exists!")

        profile2 = await parse_resume_to_profile(pdf_path, FailingLLM(), use_cache=True)
        assert profile2.full_name == profile1.full_name
