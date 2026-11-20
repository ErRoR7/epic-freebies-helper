# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from html import escape

import httpx
from loguru import logger

from models import PromotionGame
from services.epic_collection_summary_service import CollectionSummary
from services.epic_games_service import get_promotions


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def telegram_notifications_enabled() -> bool:
    return bool(_env("TELEGRAM_BOT_TOKEN") and _env("TELEGRAM_CHAT_ID"))


def _format_error(error: Exception | str | None) -> str:
    if error is None:
        return "Unknown error"

    message = str(error).strip() or type(error).__name__
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if lowered.startswith(("traceback", "file \"")):
            continue
        message = line
        break

    prefix = type(error).__name__ if isinstance(error, Exception) else ""
    if prefix and prefix not in message:
        message = f"{prefix}: {message}"

    if len(message) > 360:
        return message[:350] + "...(truncated)"
    return message


def _format_game_title(game: PromotionGame) -> str:
    return game.title or game.url or "Unknown"


def _format_telegram_game_url(url: str) -> str:
    return url


def _format_game_link(game: PromotionGame) -> str:
    title = escape(_format_game_title(game), quote=True)
    url = game.url.strip()
    if not url:
        return title
    return f'<a href="{escape(_format_telegram_game_url(url), quote=True)}">{title}</a>'


def _format_games(games: list[PromotionGame]) -> str:
    if not games:
        return "None"

    lines = []
    for game in games:
        lines.append(f"- {_format_game_link(game)}")
    return "\n".join(lines)


def build_telegram_summary_message(
    summary: CollectionSummary,
    *,
    account_label: str | None = None,
) -> str:
    if summary.error_message and summary.newly_claimed_promotions:
        status = "Partial success"
    elif summary.error_message:
        status = "Failed"
    elif summary.unconfirmed_promotions:
        status = "Needs confirmation"
    else:
        status = "Success"

    sections = ["Epic free games claim results"]

    if account_label:
        sections.extend(["", f"Account: {escape(account_label, quote=True)}"])

    sections.extend(
        [
            "",
            f"Status: {status}",
            "",
            "This week's games:",
            _format_games(summary.all_promotions),
            "",
            "Newly claimed:",
            _format_games(summary.newly_claimed_promotions),
            "",
            "Previously claimed:",
            _format_games(summary.previously_claimed_promotions),
        ]
    )

    if summary.unconfirmed_promotions:
        sections.extend(["", "Unconfirmed:", _format_games(summary.unconfirmed_promotions)])

    if summary.failed_promotions:
        sections.extend(["", "Failed to claim:", _format_games(summary.failed_promotions)])

    if summary.error_message:
        sections.extend(
            ["", "Failure reason:", escape(_format_error(summary.error_message), quote=True)]
        )

    message = "\n".join(sections)
    if len(message) > 3900:
        message = message[:3850].rsplit("\n", 1)[0]
        return message + "\n...(content too long, truncated)"
    return message


def _safe_current_promotions() -> list[PromotionGame]:
    try:
        return get_promotions()
    except Exception as err:
        logger.warning(
            "Failed to load current Epic promotions for failure notification | error_type={}",
            type(err).__name__,
        )
        return []


def failure_summary_from_exception(err: Exception) -> CollectionSummary:
    summary = getattr(err, "summary", None)
    if not isinstance(summary, CollectionSummary):
        promotions = _safe_current_promotions()
        summary = CollectionSummary(all_promotions=promotions, unconfirmed_promotions=promotions)

    if not summary.error_message:
        summary.error_message = _format_error(err)
    return summary


async def send_collection_summary_to_telegram(
    summary: CollectionSummary,
    *,
    account_label: str | None = None,
) -> None:
    token = _env("TELEGRAM_BOT_TOKEN")
    chat_id = _env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.debug("Telegram notification is not configured; skipping delivery")
        return

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": build_telegram_summary_message(summary, account_label=account_label),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as err:
        logger.warning("Telegram notification failed | status={}", err.response.status_code)
        return
    except httpx.HTTPError as err:
        logger.warning("Telegram notification failed | error_type={}", type(err).__name__)
        return
    except Exception as err:
        logger.warning(
            "Telegram notification failed before delivery | error_type={}", type(err).__name__
        )
        return

    logger.success("Telegram claim summary sent")
