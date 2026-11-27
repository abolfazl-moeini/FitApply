"""Tests for ATS resume audit feature."""

import tempfile
from pathlib import Path
import pymupdf
import pytest
from fitapply.llm import BaseLLM
from fitapply.resume import ResumeAuditResult, audit_resume
from pydantic import ValidationError


@pytest.mark.parametrize("score", [0, 100])
def test_ats_score_bounds_accept_endpoints(score):
    result = ResumeAuditResult(ats_score=score, summary_verdict="ok")
    assert result.ats_score == score


@pytest.mark.parametrize("score", [-1, 101])
def test_ats_score_bounds_reject_out_of_range(score):
    with pytest.raises(ValidationError):
        ResumeAuditResult(ats_score=score, summary_verdict="ok")


class MockAuditLLM(BaseLLM):
    async def complete(self, prompt: str, system: str | None = None) -> str:
        return """{
            "ats_score": 82,
            "summary_verdict": "Strong technical foundation but lacks quantified metrics in accomplishments.",
            "critical_issues": [
                "No metric-driven accomplishments in recent experience",
                "Skills section uses non-standard acronyms",
                "Summary is overly generic"
            ],
            "actionable_fixes": [
                "Add percentage improvements or latency reductions to project bullets",
                "Standardize technical keywords to match ATS dictionary",
                "Shorten summary to 2 punchy sentences"
            ],
            "detected_keywords": ["Python", "FastAPI", "Docker", "PostgreSQL"],
            "missing_critical_keywords": ["CI/CD", "Unit Testing", "Kubernetes"]
        }"""


@pytest.mark.asyncio
async def test_audit_resume():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "test_audit_cv.pdf"
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 72), "Sample Resume Text for ATS Audit Test")
        doc.save(str(pdf_path))
        doc.close()

        llm = MockAuditLLM()
        res = await audit_resume(pdf_path, llm)

        assert isinstance(res, ResumeAuditResult)
        assert res.ats_score == 82
        assert len(res.critical_issues) == 3
        assert len(res.actionable_fixes) == 3
        assert "Python" in res.detected_keywords
        assert "CI/CD" in res.missing_critical_keywords


@pytest.mark.asyncio
async def test_audit_empty_pdf_raises_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "empty_cv.pdf"
        doc = pymupdf.open()
        doc.new_page()  # blank page without text
        doc.save(str(pdf_path))
        doc.close()

        llm = MockAuditLLM()
        with pytest.raises(ValueError, match="No extractable text found in PDF"):
            await audit_resume(pdf_path, llm)
