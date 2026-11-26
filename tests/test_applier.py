"""Tests for BrowserApplier rules, upload modes, and indicator safety."""

import pytest
from pathlib import Path
from fitapply.applier import (
    ALREADY_APPLIED_INDICATORS,
    POST_CLICK_SUCCESS_INDICATORS,
    SITE_PROFILE_DEFAULT_PLATFORMS,
    BrowserApplier,
)
from fitapply.discovery.base import JobPosting
from fitapply.matcher import JobMatchEvaluation
from fitapply.resume import CandidateProfile


def test_already_applied_indicators_safe_from_general_english():
    sample_job_body = "We are seeking a Senior ML Engineer with experience in Applied Machine Learning and NLP."
    for ind in ALREADY_APPLIED_INDICATORS:
        assert ind not in sample_job_body


def test_site_profile_default_platforms():
    assert "jobinja" in SITE_PROFILE_DEFAULT_PLATFORMS
    assert "jobvision" in SITE_PROFILE_DEFAULT_PLATFORMS
    assert "irantalent" in SITE_PROFILE_DEFAULT_PLATFORMS


def test_post_click_success_indicators_present():
    assert any("موفقیت" in ind for ind in POST_CLICK_SUCCESS_INDICATORS)
    assert any("Application submitted" in ind for ind in POST_CLICK_SUCCESS_INDICATORS)
