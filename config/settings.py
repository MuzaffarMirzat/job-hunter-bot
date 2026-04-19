"""Environment-driven configuration for local runs and GitHub Actions."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None and value.strip() != "":
        return value.strip()
    return default


def _parse_str_list(raw: str | None, default: list[str]) -> list[str]:
    if not raw:
        return list(default)
    raw = raw.strip()
    if raw.startswith("["):
        try:
            val = json.loads(raw)
            if isinstance(val, list):
                out = [str(x).strip() for x in val if str(x).strip()]
                return out if out else list(default)
        except json.JSONDecodeError:
            pass
    if "||" in raw:
        return [x.strip() for x in raw.split("||") if x.strip()]
    return [x.strip() for x in raw.split(",") if x.strip()]


# Free / BASIC tier: one geo per fetch halves calls vs remote + united states.
DEFAULT_FETCH_LOCATIONS = ["remote"]


# Keep the default list short; use SEARCH_KEYWORDS in env for more (watch RapidAPI quota).
DEFAULT_SEARCH_KEYWORDS = [
    "test automation",
    "QA automation",
    "SDET",
    "selenium",
    "playwright",
    "cypress",
]


@dataclass(frozen=True)
class Settings:
    """``job_search_provider``: ``jsearch`` (default) or ``jobs_search`` (RapidAPI JOBS SEARCH API)."""

    jsearch_api_key: str
    job_search_provider: str
    discord_webhook_url: str
    search_keywords: tuple[str, ...]
    fetch_locations: tuple[str, ...]
    max_keywords_per_run: int | None
    max_jobs_per_post: int
    num_pages: int
    date_posted: str | None
    country: str | None
    posted_jobs_path: Path

    @staticmethod
    def load(project_root: Path) -> "Settings":
        key = _env("JSEARCH_API_KEY") or _env("JSEARCH_RAPIDAPI_KEY") or _env("RAPIDAPI_KEY")
        if not key:
            raise RuntimeError(
                "Set JSEARCH_API_KEY (or RAPIDAPI_KEY) to your RapidAPI key "
                "(same key works for JSearch and JOBS SEARCH API if you subscribe to each)."
            )

        prov_raw = (_env("JOB_SEARCH_PROVIDER", "jsearch") or "jsearch").strip().lower()
        if prov_raw in ("jobs_search", "jobs-search", "rapidapi_jobs", "google_jobs", "jobsearch"):
            job_search_provider = "jobs_search"
        else:
            job_search_provider = "jsearch"

        webhook = _env("DISCORD_WEBHOOK_URL")
        if not webhook:
            raise RuntimeError("Set DISCORD_WEBHOOK_URL to a Discord incoming webhook URL.")

        keywords = tuple(_parse_str_list(_env("SEARCH_KEYWORDS"), DEFAULT_SEARCH_KEYWORDS))
        fetch_locs = tuple(
            x.strip().lower()
            for x in _parse_str_list(_env("FETCH_LOCATIONS"), DEFAULT_FETCH_LOCATIONS)
            if x.strip()
        )
        if not fetch_locs:
            fetch_locs = tuple(DEFAULT_FETCH_LOCATIONS)

        # Default cap for BASIC/free tier; set JSEARCH_MAX_KEYWORDS=all for no cap (paid tiers).
        max_kw_raw = _env("JSEARCH_MAX_KEYWORDS", "3")
        max_keywords: int | None
        if max_kw_raw and max_kw_raw.strip().lower() in ("all", "none", "unlimited"):
            max_keywords = None
        elif max_kw_raw and max_kw_raw.strip().isdigit():
            max_keywords = max(1, int(max_kw_raw))
        else:
            max_keywords = 3

        max_jobs = int(_env("MAX_JOBS_PER_POST", "15") or "15")
        num_pages = int(_env("JOB_SEARCH_NUM_PAGES", "1") or "1")

        posted_raw = _env("POSTED_JOBS_FILE") or _env("POSTED_JOBS_STATE_FILE")
        posted_path = (
            Path(posted_raw).expanduser() if posted_raw else project_root / ".data" / "posted_jobs.json"
        )

        return Settings(
            jsearch_api_key=key,
            job_search_provider=job_search_provider,
            discord_webhook_url=webhook,
            search_keywords=keywords,
            fetch_locations=fetch_locs,
            max_keywords_per_run=max_keywords,
            max_jobs_per_post=max(1, min(max_jobs, 25)),
            num_pages=max(1, min(num_pages, 10)),
            date_posted=_env("JOB_SEARCH_DATE_POSTED", "today"),
            country=_env("JOB_SEARCH_COUNTRY"),
            posted_jobs_path=posted_path,
        )
