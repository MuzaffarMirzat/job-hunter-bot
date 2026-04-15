"""Filter and dedupe job listings before Discord."""

from __future__ import annotations

from typing import Any

from src.job_ids import stable_job_id

TITLE_SUBSTRINGS = (
    "automation",
    "sdet",
    "qa",
    "quality",
    "selenium",
    "playwright",
    "cypress",
)


def _job_title(job: dict[str, Any]) -> str:
    t = job.get("job_title") or job.get("title") or ""
    return t if isinstance(t, str) else str(t)


def _title_is_relevant(title: str) -> bool:
    lower = title.lower()
    return any(s in lower for s in TITLE_SUBSTRINGS)


def filter_jobs(jobs: list[dict[str, Any]], *, posted_job_ids: set[str]) -> list[dict[str, Any]]:
    """
    - Dedupe by ``stable_job_id`` within ``jobs`` (first occurrence wins).
    - Drop ids already in ``posted_job_ids`` (prior runs; ``posted_jobs.json``).
    - Keep only titles containing: automation, SDET, QA, quality, selenium, playwright, cypress.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for job in jobs:
        jid = stable_job_id(job)
        if jid in seen:
            continue
        if jid in posted_job_ids:
            continue
        title = _job_title(job)
        if not _title_is_relevant(title):
            continue
        seen.add(jid)
        out.append(job)
    return out
