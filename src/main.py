#!/usr/bin/env python3
"""Entry point: JSearch → filter → Discord (header, embeds, summary)."""

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
    send_summary,
)
from src.job_formatter import format_job_embed  # noqa: E402
from src.job_ids import stable_job_id  # noqa: E402
from src.jsearch import fetch_jobs, filter_jobs  # noqa: E402
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

    all_jobs: list[dict[str, Any]] = []
    for keyword in settings.search_keywords:
        try:
            remote_batch = fetch_jobs(
                keyword,
                "remote",
                api_key=settings.jsearch_api_key,
                page=1,
                num_pages=settings.num_pages,
                date_posted=settings.date_posted or "today",
                country=settings.country,
            )
            us_batch = fetch_jobs(
                keyword,
                "united states",
                api_key=settings.jsearch_api_key,
                page=1,
                num_pages=settings.num_pages,
                date_posted=settings.date_posted or "today",
                country=settings.country,
            )
        except Exception:
            logger.exception("fetch_jobs failed for keyword=%r", keyword)
            continue
        all_jobs.extend(remote_batch)
        all_jobs.extend(us_batch)

    filtered = filter_jobs(all_jobs, posted_job_ids=posted_job_ids)
    filtered.sort(key=_posted_timestamp, reverse=True)
    to_post = filtered[: settings.max_jobs_per_post]

    if not to_post:
        send_no_jobs_message()
        logger.info("No new jobs after filter.")
        return 0

    send_header(session, new_jobs_count=len(to_post))

    for job in to_post:
        embed = format_job_embed(job)
        send_job_embed(embed)

    merge_posted_job_ids(settings.posted_jobs_path, [stable_job_id(j) for j in to_post])
    send_summary(len(to_post), session)
    logger.info("Posted %s job(s), session=%s.", len(to_post), session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
