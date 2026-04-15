"""Discord incoming webhook: header, per-job embeds, summary, empty-state."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from src.job_formatter import format_header_message

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_EMBED_DELAY_SEC = 0.5


def _webhook_url() -> str:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set.")
    return url


def _post_json(body: dict[str, Any], *, timeout: float = _DEFAULT_TIMEOUT) -> None:
    resp = requests.post(_webhook_url(), json=body, timeout=timeout)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        logger.error("Discord webhook error: %s — body: %s", exc, resp.text[:500])
        raise


def send_header(session: str, *, new_jobs_count: int) -> None:
    """POST plain-text header (``content``)."""
    content = format_header_message(session, new_jobs_count=new_jobs_count)
    _post_json({"content": content[:2000], "username": "Job Hunter"})


def send_job_embed(job_embed: dict[str, Any]) -> None:
    """POST a single embed; waits 0.5s after the request to reduce rate-limit risk."""
    _post_json({"username": "Job Hunter", "embeds": [job_embed]})
    time.sleep(_EMBED_DELAY_SEC)


def send_summary(total_found: int, session: str) -> None:
    """POST closing summary line."""
    session = (session or "morning").lower()
    text = f"✅ Done! {total_found} jobs posted this {session}. Good luck everyone! 💪"
    _post_json({"content": text[:2000], "username": "Job Hunter"})


def send_no_jobs_message() -> None:
    """POST when nothing new matched filters."""
    text = "😴 No new jobs found this round. Check back next session!"
    _post_json({"content": text[:2000], "username": "Job Hunter"})


def send_webhook(
    webhook_url: str,
    *,
    content: str | None = None,
    embeds: list[dict[str, Any]] | None = None,
    username: str = "Job Hunter",
    timeout_sec: float = 30.0,
) -> None:
    """Legacy batch helper (splits embeds into chunks of 10)."""
    embeds = embeds or []
    chunks: list[list[dict[str, Any]]] = []
    for i in range(0, len(embeds), 10):
        chunks.append(embeds[i : i + 10])

    if not chunks and not (content and content.strip()):
        logger.info("Nothing to send to Discord.")
        return

    if not chunks:
        chunks = [[]]

    for idx, batch in enumerate(chunks):
        body: dict[str, Any] = {"username": username}
        if content and idx == 0:
            body["content"] = content[:2000]
        if batch:
            body["embeds"] = batch
        resp = requests.post(webhook_url, json=body, timeout=timeout_sec)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("Discord webhook error: %s — body: %s", exc, resp.text[:500])
            raise
