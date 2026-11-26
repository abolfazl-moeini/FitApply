"""Tests for Remotive and The Muse discoverers."""

import pytest
import httpx
from fitapply.discovery.global_boards import RemotiveDiscoverer, TheMuseDiscoverer, _clean_html_text


def test_clean_html_text():
    raw = "<p>Looking for a <strong>Senior Backend Engineer</strong> with Python &amp; FastAPI.</p>"
    clean = _clean_html_text(raw)
    assert "<p>" not in clean
    assert "<strong>" not in clean
    assert "Senior Backend Engineer" in clean


@pytest.mark.asyncio
async def test_remotive_discoverer_mock(monkeypatch):
    discoverer = RemotiveDiscoverer()

    sample_response = {
        "jobs": [
            {
                "id": 1001,
                "title": "Senior Python Developer",
                "company_name": "Remote Labs",
                "url": "https://remotive.com/remote-jobs/software-dev/1001",
                "candidate_required_location": "Worldwide",
                "salary": "$120,000 - $140,000",
                "description": "<p>Develop high scale microservices in Python.</p>",
            }
        ]
    }

    async def mock_get(self, url, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json=sample_response, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    jobs = await discoverer.search_jobs(keywords=["Python"], limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "remotive:1001"
    assert j.platform == "remotive"
    assert j.title == "Senior Python Developer"
    assert j.company == "Remote Labs"
    assert j.location == "Worldwide"
    assert j.salary == "$120,000 - $140,000"
    assert "<p>" not in j.description


@pytest.mark.asyncio
async def test_themuse_discoverer_mock(monkeypatch):
    discoverer = TheMuseDiscoverer()

    sample_response = {
        "results": [
            {
                "id": 2002,
                "name": "Backend Engineer",
                "company": {"name": "Acme Corp"},
                "refs": {"landing_page": "https://www.themuse.com/jobs/2002"},
                "locations": [{"name": "New York, NY"}, {"name": "Remote"}],
                "contents": "<p>Build scalable backend systems.</p>",
            }
        ]
    }

    async def mock_get(self, url, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json=sample_response, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    jobs = await discoverer.search_jobs(keywords=["Backend"], limit=5)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.id == "themuse:2002"
    assert j.platform == "themuse"
    assert j.title == "Backend Engineer"
    assert j.company == "Acme Corp"
    assert "New York" in j.location
    assert "<p>" not in j.description


@pytest.mark.asyncio
async def test_remotive_dedup_and_themuse_null_fields(monkeypatch):
    remotive = RemotiveDiscoverer()
    muse = TheMuseDiscoverer()

    remotive_resp = {
        "jobs": [
            {"id": 1001, "title": "Role A", "company_name": "Co A"},
            {"id": None, "title": "Missing ID"},
        ]
    }
    muse_resp = {
        "results": [
            {
                "id": 3003,
                "name": "Null-Safe Role",
                "company": None,
                "refs": None,
                "locations": None,
                "contents": None,
            }
        ]
    }

    async def mock_get(self, url, **kwargs):
        req = httpx.Request("GET", url)
        if "remotive" in url:
            return httpx.Response(200, json=remotive_resp, request=req)
        return httpx.Response(200, json=muse_resp, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    r_jobs = await remotive.search_jobs(keywords=["Python", "Backend"], limit=5)
    assert len(r_jobs) == 1
    assert r_jobs[0].id == "remotive:1001"

    m_jobs = await muse.search_jobs(keywords=["Backend"], limit=5)
    assert len(m_jobs) == 1
    assert m_jobs[0].company == "Employer"
    assert m_jobs[0].location == "Remote / Flexible"
