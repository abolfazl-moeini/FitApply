"""Base classes and data models for job discovery."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobPosting(BaseModel):
    """Standardized representation of a job posting across all platforms."""

    id: str = Field(description="Unique identifier (e.g. platform:post_id)")
    platform: str = Field(description="Source platform: jobinja, jobvision, irantalent, linkedin, etc.")
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    url: str = Field(description="Full direct URL to the job advertisement")
    location: Optional[str] = Field(default=None, description="City, country or remote status")
    description: str = Field(description="Full text or requirements of the job posting")
    salary: Optional[str] = Field(default=None, description="Offered salary range if available")
    posted_at: Optional[str] = Field(default=None, description="Date or time string when posted")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Original raw response from source")


class BaseDiscoverer(ABC):
    """Abstract base class for platform-specific job discovery."""

    platform_name: str = "base"

    @abstractmethod
    async def search_jobs(
        self,
        keywords: List[str],
        locations: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[JobPosting]:
        """Search and return standardized job postings."""
        pass
