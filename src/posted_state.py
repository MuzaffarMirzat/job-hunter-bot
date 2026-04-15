"""Persist posted job IDs in ``posted_jobs.json`` (ordered list, last 500 kept)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

MAX_STORED_IDS = 500


def _utc_iso_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_posted_jobs_file(path: Path) -> None:
    """Create ``{ \"job_ids\": [], \"last_updated\": \"\" }`` if missing."""
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"job_ids": [], "last_updated": ""}
    path.write_text(json.dumps(payload, indent=0), encoding="utf-8")


def load_ordered_job_ids(path: Path) -> list[str]:
    """Return job_ids in file order (newest at end after merges)."""
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read posted jobs file %s: %s", path, exc)
        return []

    if not isinstance(raw, dict):
        return []
    ids = raw.get("job_ids")
    if not isinstance(ids, list):
        return []

    out: list[str] = []
    for x in ids:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def load_posted_job_ids(path: Path) -> set[str]:
    """Set of posted ids for O(1) lookup in ``filter_jobs``."""
    return set(load_ordered_job_ids(path))


def _save_ordered(path: Path, ordered_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = ordered_ids[-MAX_STORED_IDS:] if len(ordered_ids) > MAX_STORED_IDS else ordered_ids
    payload: dict[str, Any] = {
        "job_ids": trimmed,
        "last_updated": _utc_iso_timestamp(),
    }
    path.write_text(json.dumps(payload, indent=0), encoding="utf-8")


def merge_posted_job_ids(path: Path, new_ids: Iterable[str]) -> None:
    """Append new ids (preserving order), dedupe, trim to last ``MAX_STORED_IDS``."""
    ordered = load_ordered_job_ids(path)
    existing = set(ordered)
    for x in new_ids:
        s = x.strip() if isinstance(x, str) else ""
        if not s or s in existing:
            continue
        ordered.append(s)
        existing.add(s)
    _save_ordered(path, ordered)
