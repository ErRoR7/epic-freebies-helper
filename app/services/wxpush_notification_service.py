# -*- coding: utf-8 -*-
"""
WXPush (WeChat template message) notification service.

Delivers the Epic claim summary to a self-hosted wxpush deployment
(https://github.com/frankiejun/wxpush) via its ``POST /wxsend`` API.

WeChat caps template-message title fields at roughly 20 characters per field
without newlines, so the title carries a dense single-line result summary
(e.g. ``Epic:new2/7 total``). The content carries the full game list:
WeChat shows only its beginning in the native popup, and the complete message
is rendered on the wxpush ``/skin`` page when the template message is tapped.

Import boundary: this module must NOT import ``services.telegram_notification_service``
or ``services.epic_games_service`` — the test harness stubs dependencies per
module, and cross-importing another service would silently break that stubbing.
"""

import json
import os
from urllib.parse import urlsplit

import httpx
from loguru import logger

from services.epic_collection_summary_service import CollectionSummary

TITLE_FIELD_MAX_CHARS = 20
CONTENT_MAX_CHARS = 500


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def wxpush_notifications_enabled() -> bool:
    return bool(_env("WXPUSH_TOKEN") and _normalize_wxsend_endpoint())


def _normalize_wxsend_endpoint() -> str:
    """Return the full ``/wxsend`` URL, or "" when the endpoint is unusable."""
    endpoint = _env("WXPUSH_ENDPOINT")
    # Validate with an actual parse: a malformed value (e.g. "https://[broken")
    # must disable the channel, not raise later at delivery time.
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    endpoint = endpoint.rstrip("/")
    if not endpoint.endswith("/wxsend"):
        endpoint += "/wxsend"
    return endpoint


def _default_skin_base_url() -> str:
    """Fallback tap-through target: wxpush's built-in markdown skin page."""
    parts = urlsplit(_normalize_wxsend_endpoint())
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}/skin"


def _claim_status(summary: CollectionSummary) -> str:
    if summary.error_message and summary.newly_claimed_promotions:
        return "Partial success"
    if summary.error_message:
        return "Failed"
    if summary.unconfirmed_promotions:
        return "Needs confirmation"
    return "Success"


def _clip_field(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars]


def _first_error_line(error: str) -> str:
    for line in error.splitlines():
        line = line.strip()
        if line:
            return line
    return error.strip()


def _format_games(games) -> str:
    if not games:
        return "None"
    return "\n".join(f"- {game.title or game.url or 'Unknown'}" for game in games)


def build_wxpush_title(summary: CollectionSummary) -> str:
    """
    Dense single-line title, hard-clipped to the WeChat field limit.

    Shapes:
    - all claimed:            ``Epic:new2/7 total``
    - all owned already:      ``Epic:owned/7 total``
    - partial / unconfirmed:  ``Epic:new2 fail1`` / ``...new2 pending1``
    - total failure:          ``Epic failed:password error...``
    """
    status = _claim_status(summary)
    prefix = "Epic"
    n_all = len(summary.all_promotions)
    n_new = len(summary.newly_claimed_promotions)
    n_failed = len(summary.failed_promotions)
    n_unconfirmed = len(summary.unconfirmed_promotions)

    if status == "Failed":
        reason = _first_error_line(summary.error_message) or "unknown reason"
        return _clip_field(f"{prefix} failed:{reason}", TITLE_FIELD_MAX_CHARS)

    segments = []
    if n_new:
        segments.append(f"new{n_new}")
    elif n_all and status == "Success":
        segments.append("owned")
    if n_failed:
        segments.append(f"fail{n_failed}")
    if n_unconfirmed:
        segments.append(f"pending{n_unconfirmed}")
    if status == "Partial success" and not n_failed and not n_unconfirmed:
        segments.append("partial")

    tail = ""
    if not segments:
        segments.append(f"{n_all} total")
    elif not n_failed and not n_unconfirmed and status != "Partial success":
        tail = f"/{n_all} total"

    return _clip_field(f"{prefix}:{' '.join(segments)}{tail}", TITLE_FIELD_MAX_CHARS)


def build_wxpush_content(summary: CollectionSummary, *, account_label: str | None = None) -> str:
    """Full plain-text run report (markdown-lite), truncated at a safe size."""
    lines = []
    if account_label:
        lines.append(f"Account: {account_label}")
    lines.append(f"Status: {_claim_status(summary)}")

    sections = (
        ("This week's games", summary.all_promotions),
        ("Newly claimed", summary.newly_claimed_promotions),
        ("Previously claimed", summary.previously_claimed_promotions),
    )
    for heading, games in sections:
        lines.extend([f"{heading}:", _format_games(games)])
    if summary.unconfirmed_promotions:
        lines.extend(["Unconfirmed:", _format_games(summary.unconfirmed_promotions)])
    if summary.failed_promotions:
        lines.extend(["Failed to claim:", _format_games(summary.failed_promotions)])
    if summary.error_message:
        lines.append(f"Failure reason: {_first_error_line(summary.error_message)}")

    message = "\n".join(lines)
    if len(message) > CONTENT_MAX_CHARS:
        keep = CONTENT_MAX_CHARS - len("...(truncated)")
        message = message[:keep].rsplit("\n", 1)[0] + "\n...(truncated)"
    return message


def _success_message(text: str) -> str | None:
    """Confirm a wxpush response actually delivered, returning its msg.

    wxpush answers a successful ``/wxsend`` call with JSON whose ``msg`` starts
    with "Successfully sent messages"; anything else (an HTML skin page, a
    proxy error page, a malformed body) must not be reported as a delivery.
    """
    try:
        body = json.loads(text)
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    msg = body.get("msg")
    if not isinstance(msg, str) or not msg.startswith("Successfully sent messages"):
        return None
    return msg


async def send_collection_summary_to_wxpush(
    summary: CollectionSummary, *, account_label: str | None = None
) -> None:
    if not wxpush_notifications_enabled():
        logger.debug("WXPush notification is not configured; skipping delivery")
        return

    # Endpoint parsing, message construction and delivery all sit under the
    # same notification-only protection: a config or transport problem must
    # never surface as a claim-task failure.
    try:
        endpoint = _normalize_wxsend_endpoint()
        payload: dict[str, object] = {
            "title": build_wxpush_title(summary),
            "content": build_wxpush_content(summary, account_label=account_label),
        }
        if userid := _env("WXPUSH_USERID"):
            payload["userid"] = userid
        if template_id := _env("WXPUSH_TEMPLATE_ID"):
            payload["template_id"] = template_id
        if base_url := _env("WXPUSH_BASE_URL") or _default_skin_base_url():
            payload["base_url"] = base_url

        headers = {"Authorization": _env("WXPUSH_TOKEN")}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as err:
        logger.warning("WXPush notification failed | status={}", err.response.status_code)
        return
    except httpx.HTTPError as err:
        logger.warning("WXPush notification failed | error_type={}", type(err).__name__)
        return
    except Exception as err:
        logger.warning(
            "WXPush notification failed before delivery | error_type={}", type(err).__name__
        )
        return

    # Reading and confirming the response must stay under notification-level
    # protection too: an unreadable body must not surface as a claim failure.
    try:
        text = response.text
        msg = _success_message(text)
    except Exception as err:
        logger.warning(
            "WXPush notification delivered but response could not be read | error_type={}",
            type(err).__name__,
        )
        return

    if msg:
        logger.success("WXPush claim summary sent | msg={}", msg)
    else:
        logger.warning(
            "WXPush notification delivered but response did not confirm success | status={}",
            response.status_code,
        )
