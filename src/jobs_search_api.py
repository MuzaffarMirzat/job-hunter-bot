"""RapidAPI JOBS SEARCH API (jobs-search-api.p.rapidapi.com) — temporary alternative to JSearch."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class JobsSearchQuotaExceeded(Exception):
    """HTTP 429 from Jobs Search API (monthly quota, rate limits)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


RAPID_HOST = "jobs-search-api.p.rapidapi.com"
SEARCH_URL = f"https://{RAPID_HOST}/jobs/search"


def _map_date_posted(jsearch_value: str | None) -> str:
    """Map JSearch-style ``date_posted`` to this API's filter values."""
    if not jsearch_value:
        return "day"
    v = jsearch_value.strip().lower()
    if v in ("today", "day", "24h", "24hours"):
        return "day"
    if v in ("3days", "3_days", "last3days"):
        return "3days"
    if v in ("week", "7days"):
        return "week"
    if v in ("month", "30days"):
        return "month"
    return v if v in ("day", "3days", "week", "month") else "day"


def _extract_jobs_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs")
    if isinstance(jobs, list):
        return [x for x in jobs if isinstance(x, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        inner = data.get("jobs")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def _has_next_page(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    if isinstance(data, dict) and data.get("has_next_page") is True:
        return True
    return False


def _primary_apply_url(raw: dict[str, Any]) -> str | None:
    direct = raw.get("apply_link")
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
    """Map provider fields to the JSearch-like shape used by filters, embeds, and ids."""
    job_id = raw.get("job_id")
    title = raw.get("title") or raw.get("job_title")
    company = raw.get("company") or raw.get("employer_name")
    location = raw.get("location")
    apply_url = _primary_apply_url(raw)

    job_city: str | None = None
    job_state: str | None = None
    if isinstance(location, str) and location.strip():
        parts = [p.strip() for p in location.split(",") if p.strip()]
        if len(parts) >= 2:
            job_city, job_state = parts[0], parts[1]
        elif len(parts) == 1:
            job_city = parts[0]

    salary = raw.get("salary")
    salary_str = salary.strip() if isinstance(salary, str) and salary.strip() else None

    posted = raw.get("posted_date") or raw.get("date_posted")

    is_remote = raw.get("is_remote")
    if is_remote is None and isinstance(location, str):
        is_remote = "remote" in location.lower()

    emp = raw.get("employment_type") or raw.get("type")

    out: dict[str, Any] = {
        "job_id": job_id if isinstance(job_id, str) and job_id.strip() else None,
        "job_title": title if isinstance(title, str) else str(title or ""),
        "employer_name": company if isinstance(company, str) else str(company or ""),
        "job_apply_link": apply_url,
        "job_google_link": apply_url,
        "apply_link": apply_url,
        "job_city": job_city,
        "job_state": job_state,
        "job_country": None,
        "job_is_remote": bool(is_remote) if is_remote is not None else None,
        "job_employment_type": emp if isinstance(emp, str) else None,
        "job_salary": salary_str,
        "job_min_salary": None,
        "job_max_salary": None,
        "job_posted_at": posted if isinstance(posted, str) else None,
        "job_posted_at_datetime_utc": None,
        "job_posted_at_timestamp": None,
        "_source_api": "jobs_search_api",
    }
    return {k: v for k, v in out.items() if v is not None}


def _fetch_page(
    *,
    api_key: str,
    query: str,
    page: int,
    date_posted: str,
    employment_type: str | None,
    remote_only: bool | None,
    timeout_sec: float,
) -> tuple[list[dict[str, Any]], bool]:
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPID_HOST,
    }
    params: dict[str, Any] = {
        "query": query,
        "page": str(max(1, page)),
        "date_posted": date_posted,
    }
    if employment_type:
        params["type"] = employment_type
    if remote_only is True:
        params["work_from_home"] = "true"

    resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=timeout_sec)
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
        return [], False

    if not isinstance(payload, dict):
        return [], False

    raw_list = _extract_jobs_list(payload)
    normalized = [_normalize_record(j) for j in raw_list]
    return normalized, _has_next_page(payload)


def search_jobs(
    *,
    api_key: str,
    query: str,
    page: int = 1,
    date_posted: str = "day",
    employment_type: str | None = "full-time",
    remote_only: bool | None = None,
    timeout_sec: float = 30.0,
) -> list[dict[str, Any]]:
    """Single-page search (normalized job dicts)."""
    jobs, _ = _fetch_page(
        api_key=api_key,
        query=query,
        page=page,
        date_posted=date_posted,
        employment_type=employment_type,
        remote_only=remote_only,
        timeout_sec=timeout_sec,
    )
    return jobs


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
    Same call pattern as ``src.jsearch.fetch_jobs`` — one or more pages, JSearch-like job dicts out.

    Note: ``country`` is accepted for signature parity; the upstream API may ignore it.
    """
    _ = country
    kw = (keyword or "").strip()
    loc_raw = (location or "").strip()
    loc_lower = loc_raw.lower()
    remote_only: bool | None = True if loc_lower == "remote" else (False if loc_lower == "onsite" else None)

    query = f"{kw} engineer {loc_raw}".strip()
    mapped_date = _map_date_posted(date_posted)

    merged: list[dict[str, Any]] = []
    max_pages = max(1, min(int(num_pages or 1), 5))
    start_page = max(1, int(page or 1))

    for offset in range(max_pages):
        current_page = start_page + offset
        batch, has_next = _fetch_page(
            api_key=api_key,
            query=query,
            page=current_page,
            date_posted=mapped_date,
            employment_type="full-time",
            remote_only=remote_only,
            timeout_sec=timeout_sec,
        )
        merged.extend(batch)
        if not batch:
            break
        if offset + 1 >= max_pages:
            break
        if not has_next:
            break

    return merged
