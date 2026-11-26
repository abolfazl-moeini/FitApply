"""SQLite persistent storage for tracking job applications, fit scores, and history."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from fitapply.discovery.base import JobPosting

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/jobs.db")


class JobStore:
    """SQLite-backed application tracker and deduplication store."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables if they do not exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS job_applications (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    url TEXT NOT NULL,
                    location TEXT,
                    salary TEXT,
                    status TEXT NOT NULL,  -- discovered, skipped, dry_run, applied, failed
                    fit_score INTEGER DEFAULT NULL,
                    fit_reasons TEXT DEFAULT NULL,
                    missing_skills TEXT DEFAULT NULL,
                    cover_letter TEXT DEFAULT NULL,
                    applied_at TIMESTAMP DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT DEFAULT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_platform ON job_applications(platform);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON job_applications(status);")

    def is_job_seen(self, job_id: str) -> bool:
        """Check if job has already been discovered or applied to."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT 1 FROM job_applications WHERE id = ?", (job_id,))
            return cur.fetchone() is not None

    def record_discovery(self, job: JobPosting, status: str = "discovered") -> None:
        """Save newly discovered job posting."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO job_applications (
                    id, platform, title, company, url, location, salary, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    job.id,
                    job.platform,
                    job.title,
                    job.company,
                    job.url,
                    job.location,
                    job.salary,
                    status,
                    datetime.now().isoformat(),
                ),
            )

    def record_match_result(
        self,
        job_id: str,
        fit_score: int,
        fit_reasons: str,
        missing_skills: List[str],
        cover_letter: str,
        status: str,
    ) -> None:
        """Update job matching score and evaluation."""
        import json

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE job_applications
                SET fit_score = ?,
                    fit_reasons = ?,
                    missing_skills = ?,
                    cover_letter = ?,
                    status = ?
                WHERE id = ?;
                """,
                (
                    fit_score,
                    fit_reasons,
                    json.dumps(missing_skills, ensure_ascii=False),
                    cover_letter,
                    status,
                    job_id,
                ),
            )

    def record_application(self, job_id: str, status: str = "applied", notes: Optional[str] = None) -> None:
        """Mark job as applied (or dry_run / failed)."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE job_applications
                SET status = ?,
                    applied_at = ?,
                    notes = ?
                WHERE id = ?;
                """,
                (status, datetime.now().isoformat(), notes, job_id),
            )

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics of jobs tracked."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM job_applications
                GROUP BY status;
                """
            )
            rows = cur.fetchall()
            status_counts = {row["status"]: row["count"] for row in rows}

            cur = conn.execute("SELECT COUNT(*) as total FROM job_applications;")
            total = cur.fetchone()["total"]

            cur = conn.execute(
                "SELECT COUNT(*) as applied_today FROM job_applications "
                "WHERE status = 'applied' AND date(applied_at) = date('now', 'localtime');"
            )
            applied_today = cur.fetchone()["applied_today"]

            return {
                "total": total,
                "applied_today": applied_today,
                "by_status": status_counts,
            }

    def get_recent_jobs(
        self,
        limit: int = 20,
        min_score: Optional[int] = None,
        status_filter: Optional[str] = None,
        sort_by: str = "created_at",
    ) -> List[Dict[str, Any]]:
        """Return tracked or applied jobs with optional filters and sorting."""
        query = """
            SELECT id, platform, title, company, url, location, salary, status,
                   fit_score, fit_reasons, missing_skills, cover_letter, applied_at, created_at, notes
            FROM job_applications
            WHERE 1=1
        """
        params: List[Any] = []

        if min_score is not None:
            query += " AND fit_score >= ?"
            params.append(min_score)

        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)

        if sort_by == "fit_score":
            query += " ORDER BY fit_score DESC NULLS LAST, created_at DESC"
        else:
            query += " ORDER BY created_at DESC"

        query += " LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
