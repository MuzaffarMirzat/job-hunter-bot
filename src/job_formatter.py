"""Format job data and session headers for Discord."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytz

HUNT_TOPIC = "Test Automation"
SEPARATOR = "━" * 28

_EMBED_BLUE = 3447003


def _first(*values: object | None) -> str | None:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _format_salary(job: dict[str, Any]) -> str:
    lo = job.get("job_min_salary")
    hi = job.get("job_max_salary")
    cur = _first(job.get("job_salary"))
    if lo is not None and hi is not None:
        try:
            lf, hf = float(lo), float(hi)
            if lf.is_integer() and hf.is_integer():
                return f"${int(lf):,} - ${int(hf):,}"
            return f"${lf:,.0f} - ${hf:,.0f}"
        except (TypeError, ValueError):
            return f"${lo} - ${hi}"
    if cur:
        return cur
    return "Not listed"


def _format_location(job: dict[str, Any]) -> str:
    if job.get("job_is_remote") is True:
        return "Remote"
    city = _first(job.get("job_city"))
    state = _first(job.get("job_state"))
    parts = [p for p in (city, state) if p]
    if parts:
        return "/".join(parts)
    return "Remote" if job.get("job_is_remote") is not False else "Not listed"


def _format_posted(job: dict[str, Any]) -> str:
    raw = _first(job.get("job_posted_at"), job.get("job_posted_at_datetime_utc"))
    if not raw:
        return "Not listed"
    if len(raw) > 80:
        return raw[:77] + "…"
    return raw


def format_job_embed(job: dict[str, Any]) -> dict[str, Any]:
    """
    Discord embed as dict: title, description (employer), color, fields, footer.
    """
    job_title = _first(job.get("job_title"), job.get("title")) or "Job listing"
    employer = _first(job.get("employer_name"), job.get("employer_company_type")) or "—"
    apply_link = _first(job.get("job_apply_link"), job.get("job_google_link"), job.get("apply_link")) or "#"
    employment = _first(job.get("job_employment_type")) or "Not listed"
    salary = _format_salary(job)
    location = _format_location(job)
    posted = _format_posted(job)

    apply_md = f"[Click Here]({apply_link})" if apply_link and apply_link != "#" else "Not listed"

    desc = employer[:4096] if len(employer) <= 4096 else employer[:4093] + "…"

    fields: list[dict[str, Any]] = [
        {"name": "📍 Location", "value": location[:1024], "inline": False},
        {"name": "💼 Type", "value": employment[:1024], "inline": True},
        {"name": "💰 Salary", "value": salary[:1024], "inline": True},
        {"name": "🔗 Apply", "value": apply_md[:1024], "inline": False},
        {"name": "📅 Posted", "value": posted[:1024], "inline": False},
    ]

    embed: dict[str, Any] = {
        "title": job_title[:256],
        "description": desc,
        "url": apply_link if apply_link != "#" else None,
        "color": _EMBED_BLUE,
        "fields": fields,
        "footer": {"text": "Job Hunter Bot • JSearch"},
    }
    return {k: v for k, v in embed.items() if v is not None}


def format_header_message(session: str, *, new_jobs_count: int) -> str:
    """
    session: ``morning`` or ``evening``.
    Date line uses US Eastern (aligns with EST-oriented cron commentary).
    """
    session = (session or "morning").lower()
    if session == "evening":
        lead = f"🌆 Evening Job Hunt — {HUNT_TOPIC}"
    else:
        lead = f"🌅 Morning Job Hunt — {HUNT_TOPIC}"

    tz = pytz.timezone("America/New_York")
    now = datetime.now(tz)
    date_human = f"{now.strftime('%A, %B')} {now.day}, {now.year}"

    lines = [
        lead,
        SEPARATOR,
        f"📅 {date_human}",
        "🔍 Searching: Remote + United States | All Levels",
        f"💼 Found {new_jobs_count} new jobs for you!",
        "",
    ]
    return "\n".join(lines)
