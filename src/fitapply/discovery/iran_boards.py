"""Job discovery implementations for Iranian job portals (Jobinja, Jobvision, IranTalent)."""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit
import logging
import urllib.parse
from urllib.parse import urljoin
from typing import Any, Dict, List, Optional
import httpx
from bs4 import BeautifulSoup

from fitapply.discovery.base import BaseDiscoverer, JobPosting

logger = logging.getLogger(__name__)


def _filter_known_locations(jobs: List[JobPosting], locations: Optional[List[str]]) -> List[JobPosting]:
    requested = [location.strip().casefold() for location in (locations or []) if location and location.strip()]
    if not requested:
        return jobs
    filtered = []
    for job in jobs:
        actual = (job.location or "").strip().casefold()
        # Preserve records with no usable location; do not invent a location.
        if not actual or any(location in actual for location in requested):
            filtered.append(job)
    return filtered

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fa,en;q=0.9",
}


def _extract_post_id(url: str) -> str:
    """Safely extract clean post ID from URL without trailing slashes or query parameters."""
    clean = urlsplit(url).path.rstrip("/")
    segment = clean.split("/")[-1] if "/" in clean else clean
    if not segment or segment in ("jobs", "job", "jobpost"):
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return segment


class JobinjaDiscoverer(BaseDiscoverer):
    """Scraper for Jobinja (jobinja.ir)."""

    platform_name = "jobinja"
    BASE_URL = "https://jobinja.ir"

    async def search_jobs(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 15,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=20.0, follow_redirects=False) as client:
            for kw in keywords:
                if len(results) >= limit:
                    break
                keyword_start = len(results)
                encoded_kw = urllib.parse.quote(kw)
                url = f"{self.BASE_URL}/jobs?filters%5Bkeywords%5D%5B0%5D={encoded_kw}"

                try:
                    resp = await client.get(url)
                    if resp.status_code in {301, 302, 303, 307, 308} or urlsplit(str(resp.url)).hostname not in {"jobinja.ir", "www.jobinja.ir"}:
                        logger.warning("Refusing off-board Jobinja search redirect")
                        continue
                    if resp.status_code != 200:
                        logger.warning("Jobinja returned %d for keyword '%s'", resp.status_code, kw)
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.find_all("li", class_=lambda c: c and "o-listView__item" in c)

                    for item in items:
                        if len(results) >= limit:
                            break

                        title_el = item.find("a", class_=lambda c: c and "titleLink" in c)
                        if not title_el:
                            title_el = item.find("h2")
                            if title_el:
                                title_el = title_el.find("a")
                        if not title_el:
                            continue

                        title = title_el.get_text(strip=True)
                        job_href = title_el.get("href", "")
                        if not job_href:
                            continue

                        job_url = urljoin(self.BASE_URL, job_href)
                        parsed = urlsplit(job_url)
                        if parsed.scheme != "https" or parsed.hostname not in {"jobinja.ir", "www.jobinja.ir"}:
                            continue
                        post_id = _extract_post_id(job_url)
                        job_id = f"jobinja:{post_id}"

                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Company
                        company_el = item.find("span", class_=lambda c: c and "itemCompany" in c)
                        company = company_el.get_text(strip=True) if company_el else "نامشخص"

                        # Location & meta
                        meta_items = item.find_all("li", class_=lambda c: c and "itemDetail" in c)
                        location = meta_items[0].get_text(strip=True) if meta_items else None

                        # Fetch detail page description
                        desc = await self._fetch_description(client, job_url)

                        results.append(
                            JobPosting(
                                id=job_id,
                                platform=self.platform_name,
                                title=title,
                                company=company,
                                url=job_url,
                                location=location,
                                description=desc or title,
                            )
                        )
                except Exception as e:
                    logger.error("Error searching Jobinja for '%s': %s", kw, e)

        return _filter_known_locations(results, locations)

    async def _fetch_description(self, client: httpx.AsyncClient, url: str) -> str:
        try:
            resp = await client.get(url)
            if resp.status_code in {301, 302, 303, 307, 308}:
                return ""
            parsed = urlsplit(str(resp.url))
            if parsed.scheme != "https" or parsed.hostname not in {"jobinja.ir", "www.jobinja.ir"}:
                return ""
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                desc_div = soup.find("div", class_=lambda c: c and ("jobDesc" in c or "description" in c))
                if desc_div:
                    return desc_div.get_text("\n", strip=True)
        except Exception:
            pass
        return ""


class JobvisionDiscoverer(BaseDiscoverer):
    """Discoverer for Jobvision (jobvision.ir) via internal API and web fallback."""

    platform_name = "jobvision"
    BASE_URL = "https://jobvision.ir"
    API_SEARCH_URL = "https://jobvision.ir/api/v1/jobpost/search"

    async def search_jobs(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 15,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        seen_ids: set[str] = set()

        headers = {
            **DEFAULT_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Referer": "https://jobvision.ir/jobs",
        }

        async with httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True) as client:
            for kw in keywords:
                if len(results) >= limit:
                    break

                # 1. Attempt API call
                try:
                    payload = {
                        "keyword": kw,
                        "pageSize": min(limit, 20),
                        "page": 1,
                        "sort": 0,
                    }
                    resp = await client.post(self.API_SEARCH_URL, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        job_list = data.get("data", {}).get("jobPosts", []) or data.get("items", [])
                        for item in job_list:
                            if len(results) >= limit:
                                break
                            raw_id = item.get("id") or item.get("jobPostId")
                            if raw_id is None:
                                continue
                            post_id = str(raw_id)
                            job_id = f"jobvision:{post_id}"
                            if job_id in seen_ids:
                                continue
                            title = item.get("title") or item.get("jobTitle", "نامشخص")
                            company = (
                                (item.get("company") or {}).get("name")
                                or item.get("companyName")
                                or "نامشخص"
                            )
                            job_url = f"{self.BASE_URL}/jobs/{post_id}"
                            desc = (
                                item.get("description")
                                or item.get("requirements")
                                or title
                            )
                            loc = item.get("city") or item.get("location")

                            try:
                                posting = JobPosting(
                                    id=job_id, platform=self.platform_name, title=title, company=company,
                                    url=job_url, location=str(loc) if loc else None,
                                    description=desc, raw_data=item,
                                )
                            except Exception:
                                continue
                            seen_ids.add(job_id)
                            results.append(posting)
                        if len(results) > keyword_start:
                            continue
                except Exception as e:
                    logger.debug("Jobvision API search failed (%s), attempting web fallback.", e)

                # 2. Web fallback
                try:
                    search_url = f"{self.BASE_URL}/jobs?keyword={urllib.parse.quote(kw)}"
                    resp = await client.get(search_url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        cards = soup.find_all("div", class_=lambda c: c and "job-card" in c)
                        for card in cards:
                            if len(results) >= limit:
                                break
                            title_el = card.find("a", href=lambda h: h and "/jobs/" in h)
                            if not title_el:
                                continue
                            title = title_el.get_text(strip=True)
                            href = title_el.get("href", "")
                            job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                            post_id = _extract_post_id(job_url)
                            job_id = f"jobvision:{post_id}"
                            if job_id in seen_ids:
                                continue
                            seen_ids.add(job_id)

                            results.append(
                                JobPosting(
                                    id=job_id,
                                    platform=self.platform_name,
                                    title=title,
                                    company="کارفرما در جاب‌ویژن",
                                    url=job_url,
                                    description=title,
                                )
                            )
                except Exception as e:
                    logger.error("Error searching Jobvision for '%s': %s", kw, e)

        return _filter_known_locations(results, locations)


class IranTalentDiscoverer(BaseDiscoverer):
    """Discoverer for IranTalent (irantalent.com)."""

    platform_name = "irantalent"
    BASE_URL = "https://www.irantalent.com"

    async def search_jobs(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 15,
    ) -> List[JobPosting]:
        results: List[JobPosting] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=20.0, follow_redirects=True) as client:
            for kw in keywords:
                if len(results) >= limit:
                    break
                url = f"{self.BASE_URL}/jobs?keyword={urllib.parse.quote(kw)}"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    # Look for job links
                    links = soup.find_all("a", href=lambda h: h and ("/job/" in h or "/jobs/" in h))
                    seen_urls = set()

                    for a in links:
                        if len(results) >= limit:
                            break
                        href = a.get("href", "")
                        if not href or href in seen_urls:
                            continue
                        seen_urls.add(href)
                        title = a.get_text(strip=True)
                        if len(title) < 4:
                            continue

                        job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                        post_id = _extract_post_id(job_url)
                        job_id = f"irantalent:{post_id}"
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        results.append(
                            JobPosting(
                                id=job_id,
                                platform=self.platform_name,
                                title=title,
                                company="ایران‌تلنت",
                                url=job_url,
                                description=title,
                            )
                        )
                except Exception as e:
                    logger.error("Error searching IranTalent for '%s': %s", kw, e)

        return _filter_known_locations(results, locations)
