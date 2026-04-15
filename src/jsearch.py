"""JSearch (RapidAPI) client — GET https://jsearch.p.rapidapi.com/search"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

RAPID_HOST = "jsearch.p.rapidapi.com"
SEARCH_URL = f"https://{RAPID_HOST}/search"

# Typical fields on each job dict (JSearch returns additional keys too):
# job_id, job_title, employer_name, job_city, job_state, job_country,
# job_employment_type, job_min_salary, job_max_salary, job_apply_link,
# job_posted_at, job_is_remote, ...


def search_jobs(
    *,
    api_key: str,
    query: str,
    page: int = 1,
    num_pages: int = 1,
    location: str | None = None,
    country: str | None = None,
    date_posted: str | None = None,
    employment_types: str | None = None,
    remote_jobs_only: bool | None = None,
    timeout_sec: float = 30.0,
) -> list[dict[str, Any]]:
    """
    Low-level call to JSearch `/search` with arbitrary query and optional filters.
    """
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPID_HOST,
    }
    params: dict[str, Any] = {
        "query": query,
        "page": page,
        "num_pages": num_pages,
    }
    if location:
        params["location"] = location
    if country:
        params["country"] = country
    if date_posted:
        params["date_posted"] = date_posted
    if employment_types:
        params["employment_types"] = employment_types
    if remote_jobs_only is not None:
        params["remote_jobs_only"] = str(remote_jobs_only).lower()

    resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=timeout_sec)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        logger.error("JSearch HTTP error: %s — body: %s", exc, resp.text[:500])
        raise

    payload = resp.json()
    data = payload.get("data")
    if not isinstance(data, list):
        logger.warning("Unexpected JSearch response shape: keys=%s", list(payload.keys()))
        return []

    return [item for item in data if isinstance(item, dict)]


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
    Opinionated JSearch call for this bot.

    - Headers: ``X-RapidAPI-Key``, ``X-RapidAPI-Host: jsearch.p.rapidapi.com``
    - Params:
        - ``query``: ``"{keyword} engineer {location}"`` (e.g. ``test automation engineer remote``)
        - ``page`` / ``num_pages``: 1 by default
        - ``date_posted``: ``"today"`` by default
        - ``remote_jobs_only``: ``true`` if ``location`` is ``remote``, ``false`` if ``onsite``;
          omitted for any other ``location`` (treated as a place name in the query text)

    Returns a list of job dicts (same objects JSearch returns; fields include those listed in the module docstring).
    """
    kw = (keyword or "").strip()
    loc_raw = (location or "").strip()
    loc_lower = loc_raw.lower()

    if loc_lower == "remote":
        remote_jobs_only: bool | None = True
    elif loc_lower == "onsite":
        remote_jobs_only = False
    else:
        remote_jobs_only = None

    query = f"{kw} engineer {loc_raw}".strip()

    return search_jobs(
        api_key=api_key,
        query=query,
        page=page,
        num_pages=num_pages,
        country=country,
        date_posted=date_posted,
        remote_jobs_only=remote_jobs_only,
        timeout_sec=timeout_sec,
    )


# Public orchestration API (main may ``from src.jsearch import fetch_jobs, filter_jobs``)
from src.job_filter import filter_jobs as filter_jobs  # noqa: E402
