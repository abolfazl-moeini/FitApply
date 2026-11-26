"""Browser automation applier module connecting to user's Chrome instance via CDP."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from pydantic import BaseModel, Field

from fitapply.discovery.base import JobPosting
from fitapply.llm import BaseLLM
from fitapply.matcher import JobMatchEvaluation
from fitapply.resume import CandidateProfile

logger = logging.getLogger(__name__)

# Common Persian & English selector keywords for Apply buttons
APPLY_BUTTON_TEXTS = [
    "ارسال رزومه",
    "ثبت درخواست",
    "ارسال درخواست",
    "Easy Apply",
    "ارسال سریع رزومه",
    "Apply now",
    "Apply",
]

SUBMIT_FINAL_TEXTS = [
    "تایید و ارسال",
    "ثبت نهایی",
    "ارسال نهایی",
    "تایید و ارسال رزومه",
    "Submit application",
    "Submit",
]

# Accurate indicators to prevent false-positives on general English text like "Applied ML"
ALREADY_APPLIED_INDICATORS = [
    "شما قبلاً برای این",
    "شما قبلا برای این",
    "رزومه شما ارسال شده",
    "رزومه شما با موفقیت ارسال شد",
    "درخواست شما ثبت شده",
    "درخواست همکاری شما قبلا ثبت شده",
    "You have already applied",
    "You already applied",
    "Application submitted",
]

POST_CLICK_SUCCESS_INDICATORS = [
    "با موفقیت ارسال شد",
    "رزومه شما ارسال شد",
    "درخواست شما ثبت شده",
    "درخواست با موفقیت ثبت شد",
    "Application submitted",
    "Application sent",
    "Successfully applied",
]

# Platforms where candidate resume is typically pre-hosted in profile
SITE_PROFILE_DEFAULT_PLATFORMS = {"jobinja", "jobvision", "irantalent"}


class FieldAnswer(BaseModel):
    field_key: str = Field(description="The exact key/name/id of the form field")
    value: str = Field(description="The value to fill or select")


class ScreeningAnswers(BaseModel):
    answers: List[FieldAnswer] = Field(default_factory=list)


class BrowserApplier:
    """Automates applying to jobs using a running Chrome browser session over CDP."""

    def __init__(
        self,
        cdp_url: str = "http://localhost:9222",
        timeout_seconds: int = 40,
    ):
        self.cdp_url = cdp_url
        self.timeout = timeout_seconds * 1000
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._managed_lifecycle: bool = False

    async def __aenter__(self) -> BrowserApplier:
        """Enable persistent CDP session reuse across batch applications (lazy-connected on first apply)."""
        self._managed_lifecycle = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up shared CDP browser connection."""
        self._managed_lifecycle = False
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
            self._browser = None
            self._context = None

    async def _get_or_connect_context(self) -> tuple[BrowserContext, Optional[Playwright]]:
        """Return an active BrowserContext and an optional Playwright instance owned by this call."""
        if self._context is not None and self._browser is not None and self._browser.is_connected():
            return self._context, None

        # Clean up stale connection if disconnected
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
            self._browser = None
            self._context = None

        pw = await async_playwright().start()
        try:
            browser: Browser = await pw.chromium.connect_over_cdp(self.cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
        except Exception:
            await pw.stop()
            raise

        if self._managed_lifecycle:
            self._playwright = pw
            self._browser = browser
            self._context = context
            logger.info("Connected persistent CDP session to Chrome at %s", self.cdp_url)
            return context, None

        return context, pw

    async def apply_to_job(
        self,
        job: JobPosting,
        candidate: CandidateProfile,
        evaluation: JobMatchEvaluation,
        llm: BaseLLM,
        candidate_extra: Optional[Dict[str, Any]] = None,
        resume_path: Optional[Path] = None,
        dry_run: bool = True,
        upload_mode: str = "auto",
    ) -> Dict[str, Any]:
        """Navigate to job ad, fill screening questions/cover note, and submit or simulate."""
        # Determine effective upload mode
        platform_lower = (job.platform or "").lower()
        if upload_mode == "site_profile" or (upload_mode == "auto" and platform_lower in SITE_PROFILE_DEFAULT_PLATFORMS):
            effective_upload_mode = "site_profile"
        elif upload_mode == "always_upload":
            effective_upload_mode = "always_upload"
        else:
            effective_upload_mode = "auto"

        # Check browser connection
        owned_pw: Optional[Playwright] = None
        try:
            context, owned_pw = await self._get_or_connect_context()
        except Exception as e:
            logger.error("Failed to connect to Chrome at %s: %s", self.cdp_url, e)
            return {
                "success": False,
                "status": "failed",
                "error": (
                    f"Could not connect to Chrome on {self.cdp_url}. "
                    "Make sure Chrome is running with --remote-debugging-port=9222"
                ),
            }

        page: Page = await context.new_page()

        try:
            logger.info("Opening job page: %s", job.url)
            await page.goto(job.url, timeout=self.timeout, wait_until="domcontentloaded")
            await asyncio.sleep(2)  # Allow dynamic scripts to render

            # Check if already applied
            body_text = await page.inner_text("body")
            for indicator in ALREADY_APPLIED_INDICATORS:
                if indicator in body_text:
                    logger.info("Already applied to %s (%s)", job.title, job.company)
                    return {
                        "success": True,
                        "status": "already_applied",
                        "notes": f"Detected existing application: '{indicator}'",
                    }

            # In dry-run for site_profile, check if applying would 1-click submit immediately
            if dry_run and effective_upload_mode == "site_profile":
                apply_button_visible = await self._is_apply_button_present(page)
                if not apply_button_visible:
                    return {
                        "success": False,
                        "status": "failed",
                        "error": "Could not find Apply button on page.",
                    }
                # Check if page has inline cover letter / screening fields to preview
                await self._fill_cover_letter(page, evaluation.cover_letter)
                if candidate_extra:
                    await self._fill_screening_fields(page, candidate_extra)
                logger.info("DRY-RUN (site_profile): Verified application readiness for %s (%s).", job.title, job.company)
                return {
                    "success": True,
                    "status": "dry_run",
                    "notes": "Dry-run executed successfully using site-hosted profile. No final submission performed.",
                }

            # Find and click primary Apply button
            apply_clicked = await self._click_apply_button(page)
            if not apply_clicked:
                return {
                    "success": False,
                    "status": "failed",
                    "error": "Could not find or click Apply button on page.",
                }

            await asyncio.sleep(2)

            # Check for 1-Click Apply immediate success
            post_body = await page.inner_text("body")
            for ind in POST_CLICK_SUCCESS_INDICATORS:
                if ind in post_body:
                    logger.info("1-Click apply succeeded on %s (%s)", job.title, job.company)
                    return {
                        "success": True,
                        "status": "applied",
                        "notes": f"1-Click application submitted: '{ind}'",
                    }

            # Upload resume PDF ONLY when mode is not site_profile
            if effective_upload_mode != "site_profile" and resume_path and resume_path.exists():
                await self._upload_resume_if_needed(page, resume_path)
            elif effective_upload_mode == "site_profile":
                logger.info("Using site-hosted profile for %s (no PDF upload).", job.platform)

            # Fill cover letter / message if textarea present
            await self._fill_cover_letter(page, evaluation.cover_letter)

            # Fill common screening inputs
            if candidate_extra:
                await self._fill_screening_fields(page, candidate_extra)

            # Use LLM to answer any remaining visible screening questions
            await self._answer_dynamic_questions(page, candidate, candidate_extra, llm)

            # Check for dry-run
            if dry_run:
                logger.info("DRY-RUN: Form populated for %s (%s). Skipping final submission.", job.title, job.company)
                return {
                    "success": True,
                    "status": "dry_run",
                    "notes": "Dry-run executed successfully. Form was populated without final submission.",
                }

            # Final submission
            submitted = await self._click_final_submit(page)
            await asyncio.sleep(2)

            return {
                "success": submitted,
                "status": "applied" if submitted else "failed",
                "notes": "Application submitted via browser." if submitted else "Failed on final submit button.",
            }

        except Exception as e:
            logger.exception("Error applying to job %s: %s", job.url, e)
            return {
                "success": False,
                "status": "failed",
                "error": str(e),
            }
        finally:
            try:
                await page.close()
            except Exception:
                pass
            if owned_pw is not None:
                try:
                    await owned_pw.stop()
                except Exception:
                    pass

    async def _is_apply_button_present(self, page: Page) -> bool:
        """Check if an apply button exists and is visible on page without clicking."""
        for text in APPLY_BUTTON_TEXTS:
            try:
                locator = page.get_by_text(text, exact=False).first
                if await locator.is_visible(timeout=800):
                    return True
            except Exception:
                continue

        selectors = [
            "a.c-jobView__applyButton",
            "button.c-jobView__applyButton",
            "button[data-qa*='apply']",
            "button.apply-button",
            "a[href*='apply']",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=600):
                    return True
            except Exception:
                continue
        return False

    async def _click_apply_button(self, page: Page) -> bool:
        """Find and click the initial Apply button on the job page."""
        # 1. Try text-based selectors
        for text in APPLY_BUTTON_TEXTS:
            try:
                locator = page.get_by_text(text, exact=False).first
                if await locator.is_visible(timeout=1500):
                    await locator.click()
                    logger.info("Clicked Apply button with text: '%s'", text)
                    return True
            except Exception:
                continue

        # 2. Try common CSS selectors
        selectors = [
            "a.c-jobView__applyButton",
            "button.c-jobView__applyButton",
            "button[data-qa*='apply']",
            "button.apply-button",
            "a[href*='apply']",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=1000):
                    await loc.click()
                    logger.info("Clicked Apply button via selector: %s", sel)
                    return True
            except Exception:
                continue

        return False

    async def _fill_cover_letter(self, page: Page, cover_letter: str) -> None:
        """Locate message/cover letter textarea and type the tailored message."""
        selectors = [
            "textarea[name*='message']",
            "textarea[placeholder*='پیام']",
            "textarea[placeholder*='کارفرما']",
            "textarea[name*='cover']",
            "textarea[id*='cover']",
            "textarea",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=1000):
                    await el.fill(cover_letter)
                    logger.info("Filled cover letter into textarea (%s)", sel)
                    return
            except Exception:
                continue

    async def _fill_screening_fields(self, page: Page, candidate_extra: Dict[str, Any]) -> None:
        """Fill common screening questions like salary expectation or military status if present."""
        salary = candidate_extra.get("salary_expectation_irr_monthly")
        if salary:
            salary_selectors = [
                "input[name*='salary']",
                "input[placeholder*='حقوق']",
                "input[placeholder*='مبلغ']",
            ]
            for sel in salary_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=800):
                        await el.fill(str(salary))
                        logger.info("Filled salary expectation")
                        break
                except Exception:
                    continue

    async def _upload_resume_if_needed(self, page: Page, resume_path: Path) -> None:
        """Upload resume PDF only if a visible file input is present in the application form."""
        try:
            file_inputs = page.locator("input[type='file']")
            count = await file_inputs.count()
            for i in range(count):
                inp = file_inputs.nth(i)
                if await inp.is_visible(timeout=600):
                    await inp.set_input_files(str(resume_path))
                    logger.info("Uploaded resume PDF to visible file input: %s", resume_path.name)
                    return
        except Exception as e:
            logger.debug("No visible file upload required or upload failed: %s", e)

    async def _answer_dynamic_questions(
        self,
        page: Page,
        candidate: CandidateProfile,
        candidate_extra: Optional[Dict[str, Any]],
        llm: BaseLLM,
    ) -> None:
        """Inspect unfilled visible inputs/selects and use LLM to answer screening questions."""
        try:
            fields = await page.evaluate(
                """() => {
                    const results = [];
                    const els = document.querySelectorAll('input:not([type="hidden"]):not([type="file"]):not([type="submit"]), select');
                    for (const el of els) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        if (el.tagName === 'INPUT' && el.value && el.value.trim() !== '') continue;
                        const labelEl = el.id ? document.querySelector(`label[for="${el.id}"]`) : el.closest('label');
                        const label = labelEl ? labelEl.innerText.trim() : (el.placeholder || el.name || el.id || '');
                        if (!label) continue;
                        const key = el.name || el.id || label;
                        const options = el.tagName === 'SELECT'
                            ? Array.from(el.options).map(o => o.text.trim()).filter(Boolean)
                            : [];
                        results.push({ key, tag: el.tagName, type: el.type || '', label, options });
                    }
                    return results.slice(0, 10);
                }"""
            )
            if not fields:
                return

            prompt = (
                "Fill the following job application screening fields using the candidate's info.\n"
                f"Candidate: {candidate.model_dump_json()}\n"
                f"Extra details: {json.dumps(candidate_extra or {}, ensure_ascii=False)}\n"
                f"Fields to fill: {json.dumps(fields, ensure_ascii=False)}\n"
                "Return only fields you have a confident answer for."
            )
            res = await llm.complete_structured(
                prompt=prompt,
                response_model=ScreeningAnswers,
                system="Map job application form fields to accurate candidate answers.",
            )
            for item in res.answers:
                if not item.field_key:
                    continue
                safe_key = json.dumps(item.field_key)
                filled = False

                for sel in [f"[name={safe_key}]", f"[id={safe_key}]"]:
                    try:
                        loc = page.locator(sel).first
                        if await loc.is_visible(timeout=500):
                            tag = await loc.evaluate("el => el.tagName")
                            if tag == "SELECT":
                                await loc.select_option(label=item.value)
                            else:
                                await loc.fill(item.value)
                            logger.info("LLM filled screening field '%s'", item.field_key)
                            filled = True
                            break
                    except Exception:
                        continue

                if not filled:
                    try:
                        by_label = page.get_by_label(item.field_key, exact=False).first
                        if await by_label.is_visible(timeout=500):
                            tag = await by_label.evaluate("el => el.tagName")
                            if tag == "SELECT":
                                await by_label.select_option(label=item.value)
                            else:
                                await by_label.fill(item.value)
                            logger.info("LLM filled screening field via label '%s'", item.field_key)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Dynamic screening Q&A skipped: %s", e)

    async def _click_final_submit(self, page: Page) -> bool:
        """Click the final confirm/submit button in the application modal."""
        for text in SUBMIT_FINAL_TEXTS:
            try:
                btn = page.get_by_role("button", name=text).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    logger.info("Clicked final submit button with text: '%s'", text)
                    return True
            except Exception:
                continue

        # Try generic modal submit button
        modal_submit_selectors = [
            ".modal button[type='submit']",
            ".dialog button[type='submit']",
            "form button[type='submit']",
        ]
        for sel in modal_submit_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    logger.info("Clicked final submit via selector: %s", sel)
                    return True
            except Exception:
                continue

        return False
