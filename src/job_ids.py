"""Stable identifiers for JSearch job records."""

from __future__ import annotations

import hashlib
from typing import Any


def stable_job_id(job: dict[str, Any]) -> str:
    """Prefer API job_id; otherwise hash apply link + title."""
    jid = job.get("job_id")
    if isinstance(jid, str) and jid.strip():
        return jid.strip()

    link = str(job.get("job_apply_link") or job.get("job_google_link") or job.get("apply_link") or "")
    title = str(job.get("job_title") or job.get("title") or "")
    digest = hashlib.sha256(f"{link}|{title}".encode("utf-8")).hexdigest()
    return f"derived:{digest[:40]}"
