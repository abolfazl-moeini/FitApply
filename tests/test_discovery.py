"""Tests for discovery models and platform registry."""

from fitapply.discovery import get_discoverers_for_platforms
from fitapply.discovery.base import JobPosting


def test_job_posting_model():
    posting = JobPosting(
        id="linkedin:999",
        platform="linkedin",
        title="Full Stack Engineer",
        company="Global Corp",
        url="https://linkedin.com/jobs/view/999",
        location="Remote",
        description="Remote Full Stack role with Python and TypeScript",
    )

    assert posting.id == "linkedin:999"
    assert posting.platform == "linkedin"
    assert posting.location == "Remote"


def test_get_discoverers_for_platforms():
    discoverers = get_discoverers_for_platforms(["jobinja", "jobvision", "irantalent", "linkedin"])
    names = [d.platform_name for d in discoverers]
    assert "jobinja" in names
    assert "jobvision" in names
    assert "irantalent" in names
    assert "global" in names  # LinkedIn wraps GlobalBoardsDiscoverer
