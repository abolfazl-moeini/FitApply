"""Global job board discovery using python-jobspy (LinkedIn, Indeed, Glassdoor, ZipRecruiter)."""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import math
import re
from typing import Any, Dict, List, Optional
import httpx

from fitapply.discovery.base import BaseDiscoverer, JobPosting

logger = logging.getLogger(__name__)

_HTML_STRIP_REGEX = re.compile(r"<[^>]+>")


def _clean_html_text(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    clean = html.unescape(_HTML_STRIP_REGEX.sub(" ", text or ""))
    return " ".join(clean.split()).strip()


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if math.isnan(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return default if not text or text.lower() == "nan" else text


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
        seen_ids: set[str] = set()
        query_locations = list(dict.fromkeys(locations or ["Remote"]))[:5]

        for kw in keywords:
            if len(results) >= limit:
                break

            for loc in query_locations:
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

                    try:
                        job_url = _safe_text(row.get("job_url"))
                        if not job_url:
                            continue

                        site = _safe_text(row.get("site"), "global").lower()
                        title = _safe_text(row.get("title"), "Unknown Title")
                        company = _safe_text(row.get("company"), "Unknown Company")
                        desc = _safe_text(row.get("description"), title)
                        url_hash = hashlib.sha256(job_url.encode("utf-8")).hexdigest()[:16]
                        stable_id = _safe_text(row.get("id"), url_hash)
                        job_id = f"{site}:{stable_id}"
                        if job_id in seen_ids:
                            continue
                        location_val = _safe_text(row.get("location"), loc)
                        amount = _safe_text(row.get("min_amount"))
                        salary = None
                        if amount:
                            maximum = _safe_text(row.get("max_amount"))
                            currency = _safe_text(row.get("currency"))
                            interval = _safe_text(row.get("interval"))
                            salary = f"{amount}{f'–{maximum}' if maximum else ''} {currency} {interval}".strip()
                        posting = JobPosting(
                            id=job_id, platform=site, title=title, company=company,
                            url=job_url, location=location_val, description=desc,
                            salary=salary, raw_data=row.to_dict(),
                        )
                        seen_ids.add(job_id)
                        results.append(posting)
                    except Exception as row_error:
                        logger.debug("Skipping malformed JobSpy row: %s", row_error)
              except Exception as e:
                logger.error("Error scraping global jobs for '%s' at '%s': %s", kw, loc, e)

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
        seen_ids: set[str] = set()

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

                    for item in jobs if isinstance(jobs, list) else []:
                        if len(results) >= limit:
                            break
                        if not isinstance(item, dict):
                            continue
                        try:
                            raw_id = item.get("id")
                        except Exception:
                            continue
                        if raw_id is None:
                            continue
                        post_id = str(raw_id)
                        job_id = f"remotive:{post_id}"
                        if job_id in seen_ids:
                            continue
                        title = item.get("title") or "Remote Role"
                        company = item.get("company_name") or "Remote Employer"
                        url = item.get("url") or f"https://remotive.com/remote-jobs/{post_id}"
                        loc = item.get("candidate_required_location") or "Remote"
                        requested = [x.casefold() for x in (locations or []) if x]
                        known = str(loc).strip().casefold()
                        if requested and known not in {"worldwide", "anywhere", "remote", "flexible"} and not any(x in known for x in requested):
                            continue
                        desc = _clean_html_text(item.get("description") or title)
                        salary = item.get("salary") or None

                        posting = JobPosting(
                                id=job_id,
                                platform=self.platform_name,
                                title=title,
                                company=company,
                                url=url,
                                location=loc,
                                salary=salary,
                                description=desc,
                                raw_data=item,
                        )
                        seen_ids.add(job_id)
                        results.append(posting)
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
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            for kw in keywords:
                if len(results) >= limit:
                    break
                for page in range(3):
                  if len(results) >= limit:
                    break
                  try:
                    # The official v2 documentation URL no longer publishes a contract;
                    # page is the documented pagination parameter. Filter keywords locally.
                    resp = await client.get(self.BASE_API_URL, params={"page": page})
                    if resp.status_code != 200:
                        logger.warning("The Muse API returned %d for query '%s'", resp.status_code, kw)
                        continue

                    data = resp.json()
                    items = data.get("results", []) if isinstance(data, dict) else []

                    for item in items if isinstance(items, list) else []:
                        if len(results) >= limit:
                            break
                        if not isinstance(item, dict):
                            continue

                        raw_id = item.get("id")
                        if raw_id is None:
                            continue
                        post_id = str(raw_id)
                        job_id = f"themuse:{post_id}"
                        if job_id in seen_ids:
                            continue
                        title = item.get("name") or "Job Role"
                        company = (item.get("company") or {}).get("name") or "Employer"
                        url = (item.get("refs") or {}).get("landing_page") or f"https://www.themuse.com/jobs/{post_id}"
                        locs = [l.get("name", "") for l in (item.get("locations") or []) if l and l.get("name")]
                        loc = ", ".join(locs) if locs else "Location not specified"
                        desc = _clean_html_text(item.get("contents") or title)
                        searchable = f"{title} {desc}".casefold()
                        if kw.casefold() not in searchable:
                            continue
                        requested = [x.casefold() for x in (locations or []) if x]
                        if requested and locs and not any(x in loc.casefold() for x in requested):
                            continue

                        posting = JobPosting(
                                id=job_id,
                                platform=self.platform_name,
                                title=title,
                                company=company,
                                url=url,
                                location=loc,
                                description=desc,
                                raw_data=item,
                        )
                        seen_ids.add(job_id)
                        results.append(posting)
                  except Exception as e:
                    logger.error("Error fetching from The Muse for '%s' page %d: %s", kw, page, e)

        return results
