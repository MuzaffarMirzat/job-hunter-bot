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


DEFAULT_FETCH_LOCATIONS = ["remote", "united states"]


DEFAULT_SEARCH_KEYWORDS = [
    "test automation",
    "QA automation",
    "SDET",
    "selenium",
    "playwright",
    "cypress",
    "senior automation engineer",
    "senior test automation engineer",
    "senior QA automation engineer",
    "senior SDET",
    "senior selenium engineer",
    "senior playwright engineer",
    "senior cypress engineer",
    "senior automation test engineer",
    "senior QA test engineer",
]


@dataclass(frozen=True)
class Settings:
    jsearch_api_key: str
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
            raise RuntimeError("Set JSEARCH_API_KEY to your RapidAPI key for JSearch.")

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

        max_kw_raw = _env("JSEARCH_MAX_KEYWORDS")
        max_keywords: int | None = None
        if max_kw_raw and max_kw_raw.strip().isdigit():
            max_keywords = max(1, int(max_kw_raw))

        max_jobs = int(_env("MAX_JOBS_PER_POST", "15") or "15")
        num_pages = int(_env("JOB_SEARCH_NUM_PAGES", "1") or "1")

        posted_raw = _env("POSTED_JOBS_FILE") or _env("POSTED_JOBS_STATE_FILE")
        posted_path = (
            Path(posted_raw).expanduser() if posted_raw else project_root / ".data" / "posted_jobs.json"
        )

        return Settings(
            jsearch_api_key=key,
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
