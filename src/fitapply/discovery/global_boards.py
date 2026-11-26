"""Global job board discovery using python-jobspy (LinkedIn, Indeed, Glassdoor, ZipRecruiter)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import List, Optional

from fitapply.discovery.base import BaseDiscoverer, JobPosting

logger = logging.getLogger(__name__)


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
