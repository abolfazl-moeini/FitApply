"""Tests for Iranian job boards scrapers, deduplication and ID extraction."""

import pytest
import httpx
from fitapply.discovery.iran_boards import (
    JobinjaDiscoverer,
    JobvisionDiscoverer,
    IranTalentDiscoverer,
    _extract_post_id,
)


def test_extract_post_id():
    assert _extract_post_id("https://jobinja.ir/jobs/ABC-123/") == "ABC-123"
    assert _extract_post_id("https://jobvision.ir/jobs/9988?ref=search") == "9988"
    assert _extract_post_id("https://www.irantalent.com/job/senior-dev-555/") == "senior-dev-555"
    fallback = _extract_post_id("https://jobinja.ir/jobs/")
    assert len(fallback) == 12


@pytest.mark.asyncio
async def test_jobvision_null_company_and_deduplication(monkeypatch):
    discoverer = JobvisionDiscoverer()

    sample_api_response = {
        "data": {
            "jobPosts": [
                {
                    "id": 101,
                    "title": "Backend Dev",
                    "company": None,  # Test null safety
                    "companyName": None,
                },
                {
                    "id": 101,  # Duplicate ID
                    "title": "Backend Dev",
                    "company": {"name": "Tech Corp"},
                },
            ]
        }
    }

    async def mock_post(self, url, **kwargs):
        req = httpx.Request("POST", url)
        return httpx.Response(200, json=sample_api_response, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    jobs = await discoverer.search_jobs(keywords=["Python"], limit=5)
    assert len(jobs) == 1
    assert jobs[0].id == "jobvision:101"
    assert jobs[0].company == "نامشخص"
