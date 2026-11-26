"""Global job board discovery using python-jobspy (LinkedIn, Indeed, Glassdoor, ZipRecruiter)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from fitapply.discovery.base import BaseDiscoverer, JobPosting

logger = logging.getLogger(__name__)

_HTML_STRIP_REGEX = re.compile(r"<[^>]+>")


def _clean_html_text(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    clean = _HTML_STRIP_REGEX.sub(" ", text or "")
    return " ".join(clean.split()).strip()


class GlobalBoardsDiscoverer(BaseDiscoverer):
    """Wrapper around python-jobspy for international job portals."""

    platform_name = "global"

    def __init__(self, sites: Optional[List[str]] = None):
        # Supported sites in JobSpy: "linkedin", "indeed", "glassdoor", "zip_recruiter", "google"
        self.sites = sites or ["linkedin", "indeed"]

    async def search_jobs(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 15,
    ) -> List[JobPosting]:
        try:
            from jobspy import scrape_jobs
        except ImportError:
            logger.warning("python-jobspy is not installed. Global job discovery is disabled.")
            return []

        results: List[JobPosting] = []
        loc = locations[0] if locations else "Remote"

        for kw in keywords:
            if len(results) >= limit:
                break

            try:
                # JobSpy is synchronous, run in worker thread to avoid blocking event loop
                df = await asyncio.to_thread(
                    scrape_jobs,
                    site_name=self.sites,
                    search_term=kw,
                    location=loc,
                    results_wanted=min(limit, 20),
                    hours_old=72,
                )

                if df is None or df.empty:
                    continue

                for _, row in df.iterrows():
                    if len(results) >= limit:
                        break

                    job_url = str(row.get("job_url") or "")
                    if not job_url or job_url == "nan":
                        continue

                    site = str(row.get("site") or "global").lower()
                    title = str(row.get("title") or "Unknown Title")
                    company = str(row.get("company") or "Unknown Company")
                    desc = str(row.get("description") or title)
                    url_hash = hashlib.sha256(job_url.encode("utf-8")).hexdigest()[:16]
                    raw_id = row.get("id")
                    stable_id = str(raw_id) if raw_id and str(raw_id) != "nan" else url_hash
                    job_id = f"{site}:{stable_id}"
                    location_val = str(row.get("location") or loc)

                    results.append(
                        JobPosting(
                            id=job_id,
                            platform=site,
                            title=title,
                            company=company,
                            url=job_url,
                            location=location_val,
                            description=desc,
                            raw_data=row.to_dict(),
                        )
                    )
            except Exception as e:
                logger.error("Error scraping global jobs for '%s': %s", kw, e)

        return results


class RemotiveDiscoverer(BaseDiscoverer):
    """Direct fetcher for Remotive remote jobs API (100% free, no API key required)."""

    platform_name = "remotive"
    BASE_API_URL = "https://remotive.com/api/remote-jobs"

    async def search_jobs(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 15,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            for kw in keywords:
                if len(results) >= limit:
                    break

                try:
                    resp = await client.get(
                        self.BASE_API_URL,
                        params={"search": kw, "limit": min(limit, 30)},
                    )
                    if resp.status_code != 200:
                        logger.warning("Remotive API returned %d for query '%s'", resp.status_code, kw)
                        continue

                    data = resp.json()
                    jobs = data.get("jobs", [])

                    for item in jobs:
                        if len(results) >= limit:
                            break

                        post_id = str(item.get("id"))
                        title = item.get("title") or "Remote Role"
                        company = item.get("company_name") or "Remote Employer"
                        url = item.get("url") or f"https://remotive.com/remote-jobs/{post_id}"
                        loc = item.get("candidate_required_location") or "Remote"
                        desc = _clean_html_text(item.get("description") or title)
                        salary = item.get("salary") or None

                        results.append(
                            JobPosting(
                                id=f"remotive:{post_id}",
                                platform=self.platform_name,
                                title=title,
                                company=company,
                                url=url,
                                location=loc,
                                salary=salary,
                                description=desc,
                                raw_data=item,
                            )
                        )
                except Exception as e:
                    logger.error("Error fetching from Remotive for '%s': %s", kw, e)

        return results


class TheMuseDiscoverer(BaseDiscoverer):
    """Direct fetcher for The Muse public jobs API (100% free, no API key required)."""

    platform_name = "themuse"
    BASE_API_URL = "https://www.themuse.com/api/public/jobs"

    async def search_jobs(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 15,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            for kw in keywords:
                if len(results) >= limit:
                    break

                try:
                    resp = await client.get(
                        self.BASE_API_URL,
                        params={"query": kw, "page": 1, "descending": "true"},
                    )
                    if resp.status_code != 200:
                        logger.warning("The Muse API returned %d for query '%s'", resp.status_code, kw)
                        continue

                    data = resp.json()
                    items = data.get("results", [])

                    for item in items:
                        if len(results) >= limit:
                            break

                        post_id = str(item.get("id"))
                        title = item.get("name") or "Job Role"
                        company = item.get("company", {}).get("name") or "Employer"
                        url = item.get("refs", {}).get("landing_page") or f"https://www.themuse.com/jobs/{post_id}"
                        locs = [l.get("name", "") for l in item.get("locations", []) if l.get("name")]
                        loc = ", ".join(locs) if locs else "Remote / Flexible"
                        desc = _clean_html_text(item.get("contents") or title)

                        results.append(
                            JobPosting(
                                id=f"themuse:{post_id}",
                                platform=self.platform_name,
                                title=title,
                                company=company,
                                url=url,
                                location=loc,
                                description=desc,
                                raw_data=item,
                            )
                        )
                except Exception as e:
                    logger.error("Error fetching from The Muse for '%s': %s", kw, e)

        return results
