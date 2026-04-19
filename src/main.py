#!/usr/bin/env python3
"""Entry point: job search API → filter → Discord (header, embeds, summary)."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import Settings  # noqa: E402

from src.discord_notifier import (  # noqa: E402
    send_header,
    send_job_embed,
    send_no_jobs_message,
    send_notice,
    send_summary,
)
from src.job_formatter import format_job_embed  # noqa: E402
from src.job_ids import stable_job_id  # noqa: E402
from src.jobs_search_api import JobsSearchQuotaExceeded, fetch_jobs as fetch_jobs_jobs_search  # noqa: E402
from src.jsearch import JSearchQuotaExceeded, fetch_jobs as fetch_jobs_jsearch, filter_jobs  # noqa: E402
from src.posted_state import ensure_posted_jobs_file, load_posted_job_ids, merge_posted_job_ids  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("job_hunter")


def _posted_timestamp(job: dict[str, Any]) -> float:
    """Best-effort sort key: newest first (unknown dates → 0)."""
    raw_ts = job.get("job_posted_at_timestamp")
    if isinstance(raw_ts, (int, float)):
        return float(raw_ts)
    for key in ("job_posted_at_datetime_utc", "job_posted_at"):
        raw = job.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        s = raw.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s).timestamp()
        except ValueError:
            continue
    return 0.0


def detect_session() -> str:
    """Align with scheduled runs: 10 AM EST → 15 UTC (morning); 7 PM EST → 00 UTC (evening)."""
    hour = datetime.now(timezone.utc).hour
    if hour == 15:
        return "morning"
    if hour == 0:
        return "evening"
    if hour < 20:
        return "morning"
    return "evening"


def main() -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass

    try:
        settings = Settings.load(_ROOT)
    except RuntimeError as e:
        logger.error("%s", e)
        return 1

    session = detect_session()
    ensure_posted_jobs_file(settings.posted_jobs_path)
    posted_job_ids = load_posted_job_ids(settings.posted_jobs_path)

    keywords = settings.search_keywords
    if settings.max_keywords_per_run is not None:
        keywords = keywords[: settings.max_keywords_per_run]

    use_jobs_search = settings.job_search_provider == "jobs_search"
    fetch_jobs = fetch_jobs_jobs_search if use_jobs_search else fetch_jobs_jsearch
    quota_exc = (JobsSearchQuotaExceeded, JSearchQuotaExceeded)
    source_label = "Jobs Search API" if use_jobs_search else "JSearch"

    all_jobs: list[dict[str, Any]] = []
    quota_hit = False
    for keyword in keywords:
        for location in settings.fetch_locations:
            try:
                batch = fetch_jobs(
                    keyword,
                    location,
                    api_key=settings.jsearch_api_key,
                    page=1,
                    num_pages=settings.num_pages,
                    date_posted=settings.date_posted or "today",
                    country=settings.country,
                )
            except quota_exc as exc:
                logger.warning(
                    "%s quota or rate limit — stopping further API calls: %s",
                    source_label,
                    exc.detail[:200],
                )
                quota_hit = True
                break
            except Exception:
                logger.exception("fetch_jobs failed for keyword=%r location=%r", keyword, location)
                continue
            all_jobs.extend(batch)
        if quota_hit:
            break

    if not all_jobs and quota_hit:
        if use_jobs_search:
            send_notice(
                "⚠️ **Jobs Search API / RapidAPI returned HTTP 429** (quota or rate limit). "
                "No job data was fetched this run.\n\n"
                "**Options:** wait for the monthly quota to reset, upgrade the API plan on RapidAPI, "
                "or reduce calls: `JSEARCH_MAX_KEYWORDS` (default 3), `FETCH_LOCATIONS` (default `remote`), "
                "one daily cron, `JOB_SEARCH_NUM_PAGES=1`.\n"
                "<https://rapidapi.com/rphrp1985/api/jobs-search-api>"
            )
        else:
            send_notice(
                "⚠️ **JSearch / RapidAPI returned HTTP 429** (quota or rate limit). "
                "No job data was fetched this run.\n\n"
                "**Options:** wait for your monthly quota to reset, upgrade JSearch on RapidAPI, "
                "switch to backup with `JOB_SEARCH_PROVIDER=jobs_search` (subscribe to JOBS SEARCH API), "
                "or tighten free-tier vars: `JSEARCH_MAX_KEYWORDS` (default 3), `FETCH_LOCATIONS` (default `remote`), "
                "and keep **one** daily cron in the workflow.\n"
                "<https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch>"
            )
        return 0

    filtered = filter_jobs(all_jobs, posted_job_ids=posted_job_ids)
    filtered.sort(key=_posted_timestamp, reverse=True)
    to_post = filtered[: settings.max_jobs_per_post]

    if not to_post:
        send_no_jobs_message()
        logger.info("No new jobs after filter.")
        return 0

    kw_cap = settings.max_keywords_per_run
    cap_txt = "all keywords" if kw_cap is None else f"first {kw_cap} keywords"
    scope = (
        f"Searching: {', '.join(settings.fetch_locations)} • {cap_txt} per location • {source_label}"
    )
    send_header(session, new_jobs_count=len(to_post), scope_line=scope)

    for job in to_post:
        embed = format_job_embed(job)
        send_job_embed(embed)

    merge_posted_job_ids(settings.posted_jobs_path, [stable_job_id(j) for j in to_post])
    send_summary(len(to_post), session)
    logger.info("Posted %s job(s), session=%s.", len(to_post), session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
