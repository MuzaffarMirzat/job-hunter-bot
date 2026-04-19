"""RapidAPI JOBS SEARCH API — POST /getjobs (JobSpy-style body)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)


class JobsSearchQuotaExceeded(Exception):
    """HTTP 429 from Jobs Search API (monthly quota, rate limits)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


RAPID_HOST = "jobs-search-api.p.rapidapi.com"
GETJOBS_URL = f"https://{RAPID_HOST}/getjobs"

# US-focused boards; naukri/bayt often add noise for ``United States`` searches.
DEFAULT_SITE_NAMES = [
    "linkedin",
    "indeed",
    "zip_recruiter",
    "glassdoor",
]


def _hours_old_from_date_posted(jsearch_value: str | None) -> int:
    """Map JSearch-style ``JOB_SEARCH_DATE_POSTED`` to ``hours_old`` for this API."""
    if not jsearch_value:
        return 48
    v = jsearch_value.strip().lower()
    if v in ("today", "day", "24h", "24hours"):
        return 24
    if v in ("yesterday",):
        return 48
    if v in ("3days", "3_days", "last3days"):
        return 72
    if v in ("week", "7days"):
        return 168
    if v in ("month", "30days"):
        return 720
    return 72


def _effective_hours_old(date_posted: str | None) -> int:
    """``JOBS_SEARCH_HOURS_OLD`` integer override (1–720), else mapped from ``date_posted``."""
    raw = os.environ.get("JOBS_SEARCH_HOURS_OLD")
    if raw is not None and raw.strip().isdigit():
        return max(1, min(int(raw.strip()), 720))
    return _hours_old_from_date_posted(date_posted)


def _employer_skip_substrings() -> tuple[str, ...]:
    """
    Drop listings whose company name contains any of these substrings (case-insensitive).

    Default ``amazon`` reduces repetitive megacorp spam; set ``JOBS_SEARCH_SKIP_EMPLOYER_SUBSTR=none``
    to disable, or ``acme,contoso`` for a custom list.
    """
    raw = os.environ.get("JOBS_SEARCH_SKIP_EMPLOYER_SUBSTR")
    if raw is None:
        return ("amazon",)
    t = raw.strip().lower()
    if t in ("", "none", "off", "-", "false"):
        return ()
    return tuple(x.strip().lower() for x in raw.split(",") if x.strip())


def _country_indeed(country: str | None) -> str:
    """Indeed/Glassdoor expect names like ``USA`` (see JobSpy docs)."""
    if not country:
        return "USA"
    c = country.strip().upper()
    if c in ("US", "USA", "UNITED STATES"):
        return "USA"
    if c in ("UK", "GB"):
        return "UK"
    return country.strip()


def _parse_posted_to_utc_ts(val: Any) -> float | None:
    """Parse JobSpy / API ``date_posted`` into a UTC Unix timestamp when possible."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    s_iso = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        pass
    if len(s) >= 10:
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            pass
    return None


def _filter_raw_by_recency(raw_list: list[dict[str, Any]], max_hours: int) -> list[dict[str, Any]]:
    """
    Drop rows with a parseable ``date_posted`` older than ``max_hours`` (with small slack).

    Indeed/LinkedIn often ignore ``hours_old`` when combined with other filters; this is a safety net.
    """
    if max_hours <= 0:
        return raw_list
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1, int(max_hours * 1.15)))
    cutoff_ts = cutoff.timestamp()
    kept: list[dict[str, Any]] = []
    dropped = 0
    for raw in raw_list:
        val = raw.get("date_posted") or raw.get("DATE_POSTED") or raw.get("posted_date")
        ts = _parse_posted_to_utc_ts(val)
        if ts is not None and ts < cutoff_ts:
            dropped += 1
            continue
        kept.append(raw)
    if dropped:
        logger.info("Jobs Search API: dropped %s listing(s) older than ~%s h (parsed date_posted).", dropped, max_hours)
    return kept


def _filter_by_employer_skip(jobs: list[dict[str, Any]], patterns: tuple[str, ...]) -> list[dict[str, Any]]:
    if not patterns:
        return jobs
    out: list[dict[str, Any]] = []
    dropped = 0
    for job in jobs:
        emp = (job.get("employer_name") or "").lower()
        if any(p and p in emp for p in patterns):
            dropped += 1
            continue
        out.append(job)
    if dropped:
        logger.info("Jobs Search API: dropped %s listing(s) matching JOBS_SEARCH_SKIP_EMPLOYER_SUBSTR.", dropped)
    return out


def _extract_jobs_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("jobs", "results", "listings", "job_listings", "data"):
        v = payload.get(key)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return [x for x in v if isinstance(x, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        for inner_key in ("jobs", "results", "listings"):
            inner = data.get(inner_key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
    return []


def _first_str(*vals: object | None) -> str | None:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _primary_apply_url(raw: dict[str, Any]) -> str | None:
    direct = raw.get("apply_link") or raw.get("job_url") or raw.get("JOB_URL")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    links = raw.get("apply_links")
    if not isinstance(links, list):
        return None
    primaries: list[str] = []
    others: list[str] = []
    for item in links:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        if item.get("is_primary") is True:
            primaries.append(url.strip())
        else:
            others.append(url.strip())
    if primaries:
        return primaries[0]
    return others[0] if others else None


def _normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Map provider / JobSpy-shaped rows to the JSearch-like dict used downstream."""
    job_id = raw.get("job_id") or raw.get("id")
    if job_id is not None and not isinstance(job_id, str):
        job_id = str(job_id)

    title = _first_str(
        raw.get("title"),
        raw.get("TITLE"),
        raw.get("job_title"),
    ) or ""

    company = _first_str(
        raw.get("company"),
        raw.get("COMPANY"),
        raw.get("employer_name"),
    ) or ""

    apply_url = _primary_apply_url(raw) or _first_str(
        raw.get("url"),
        raw.get("link"),
    )

    job_city: str | None = None
    job_state: str | None = None
    loc = raw.get("location")
    if isinstance(loc, dict):
        job_city = _first_str(loc.get("city"), loc.get("CITY"))
        job_state = _first_str(loc.get("state"), loc.get("STATE"))
    elif isinstance(loc, str) and loc.strip():
        parts = [p.strip() for p in loc.split(",") if p.strip()]
        if len(parts) >= 2:
            job_city, job_state = parts[0], parts[1]
        elif len(parts) == 1:
            job_city = parts[0]

    salary_str = _first_str(raw.get("salary"))
    min_a = raw.get("min_amount") or raw.get("MIN_AMOUNT")
    max_a = raw.get("max_amount") or raw.get("MAX_AMOUNT")

    posted = _first_str(
        raw.get("date_posted"),
        raw.get("DATE_POSTED"),
        raw.get("posted_date"),
    )

    is_remote = raw.get("is_remote")
    if is_remote is None:
        is_remote = raw.get("IS_REMOTE")

    emp = _first_str(
        raw.get("job_type"),
        raw.get("JOB_TYPE"),
        raw.get("employment_type"),
    )

    posted_ts: float | None = None
    raw_dp = raw.get("date_posted") or raw.get("DATE_POSTED") or raw.get("posted_date")
    ts = _parse_posted_to_utc_ts(raw_dp)
    if ts is not None:
        posted_ts = ts

    out: dict[str, Any] = {
        "job_id": job_id if isinstance(job_id, str) and job_id.strip() else None,
        "job_title": title,
        "employer_name": company,
        "job_apply_link": apply_url,
        "job_google_link": apply_url,
        "apply_link": apply_url,
        "job_city": job_city,
        "job_state": job_state,
        "job_country": None,
        "job_is_remote": bool(is_remote) if is_remote is not None else None,
        "job_employment_type": emp,
        "job_salary": salary_str,
        "job_min_salary": min_a,
        "job_max_salary": max_a,
        "job_posted_at": posted,
        "job_posted_at_datetime_utc": None,
        "job_posted_at_timestamp": posted_ts,
        "_source_api": "jobs_search_api",
    }
    return {k: v for k, v in out.items() if v is not None}


def _post_getjobs(
    *,
    api_key: str,
    body: dict[str, Any],
    timeout_sec: float,
    recency_hours: int,
) -> list[dict[str, Any]]:
    headers = {
        "Content-Type": "application/json",
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPID_HOST,
    }
    resp = requests.post(GETJOBS_URL, headers=headers, json=body, timeout=timeout_sec)
    if resp.status_code == 429:
        snippet = (resp.text or "")[:500]
        logger.warning("Jobs Search API 429 — %s", snippet)
        raise JobsSearchQuotaExceeded(snippet)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        logger.error("Jobs Search API HTTP error: %s — body: %s", exc, (resp.text or "")[:500])
        raise

    try:
        payload = resp.json()
    except ValueError:
        logger.warning("Jobs Search API non-JSON body")
        return []

    raw_list = _extract_jobs_list(payload)
    if not raw_list and isinstance(payload, dict):
        logger.warning(
            "Jobs Search API: no job list in response; keys=%s",
            list(payload.keys())[:20],
        )

    raw_list = _filter_raw_by_recency(raw_list, recency_hours)
    normalized = [_normalize_record(j) for j in raw_list]
    return _filter_by_employer_skip(normalized, _employer_skip_substrings())


def _build_getjobs_body(
    *,
    search_term: str,
    location: str,
    country_indeed: str,
    results_wanted: int,
    hours_old: int,
    page: int,
) -> dict[str, Any]:
    """
    Build JSON for ``/getjobs``.

    JobSpy / Indeed: **do not** send ``job_type`` or ``is_remote`` together with ``hours_old`` — Indeed
    then effectively drops the time filter and you get very old rows. Put ``remote`` in ``search_term``
    instead when you mean remote work.
    """
    body: dict[str, Any] = {
        "search_term": search_term,
        "location": location,
        "country_indeed": country_indeed,
        "results_wanted": max(1, min(int(results_wanted), 100)),
        "site_name": list(DEFAULT_SITE_NAMES),
        "distance": 50,
        "hours_old": max(1, min(int(hours_old), 720)),
        "linkedin_fetch_description": False,
    }
    page_off = max(0, (max(1, int(page or 1)) - 1) * 25)
    if page_off:
        body["offset"] = page_off
    return body


def search_jobs(
    *,
    api_key: str,
    query: str,
    page: int = 1,
    date_posted: str = "day",
    employment_type: str | None = "full-time",
    remote_only: bool | None = None,
    timeout_sec: float = 30.0,
    country_indeed: str = "USA",
    results_wanted: int = 20,
) -> list[dict[str, Any]]:
    """
    Single POST ``/getjobs`` (``employment_type`` ignored — recency mode uses ``hours_old`` only).
    """
    _ = employment_type
    hours_old = _effective_hours_old(date_posted)
    q = (query or "").strip()
    if remote_only is True and "remote" not in q.lower():
        q = f"{q} remote".strip()
    body = _build_getjobs_body(
        search_term=q,
        location="United States",
        country_indeed=country_indeed,
        results_wanted=max(1, min(int(results_wanted), 100)),
        hours_old=hours_old,
        page=page,
    )
    return _post_getjobs(api_key=api_key, body=body, timeout_sec=timeout_sec, recency_hours=hours_old)


def fetch_jobs(
    keyword: str,
    location: str,
    *,
    api_key: str,
    page: int = 1,
    num_pages: int = 1,
    date_posted: str = "today",
    country: str | None = None,
    timeout_sec: float = 30.0,
) -> list[dict[str, Any]]:
    """
    Same call pattern as ``src.jsearch.fetch_jobs`` — POST ``/getjobs``, normalized job dicts out.
    """
    kw = (keyword or "").strip()
    loc_raw = (location or "").strip()
    loc_lower = loc_raw.lower()

    if loc_lower == "remote":
        loc_str = "United States"
        want_remote_in_query = True
    elif loc_lower == "onsite":
        loc_str = "United States"
        want_remote_in_query = False
    else:
        loc_str = loc_raw if loc_raw else "United States"
        want_remote_in_query = False

    search_term = f"{kw} automation engineer".strip()
    if want_remote_in_query and "remote" not in search_term.lower():
        search_term = f"{search_term} remote".strip()

    hours_old = _effective_hours_old(date_posted)
    country_indeed = _country_indeed(country)

    results_wanted = min(max(10, 15 * int(num_pages or 1)), 100)

    body = _build_getjobs_body(
        search_term=search_term,
        location=loc_str,
        country_indeed=country_indeed,
        results_wanted=results_wanted,
        hours_old=hours_old,
        page=max(1, int(page or 1)),
    )

    return _post_getjobs(
        api_key=api_key,
        body=body,
        timeout_sec=timeout_sec,
        recency_hours=hours_old,
    )
