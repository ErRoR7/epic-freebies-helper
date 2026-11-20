# -*- coding: utf-8 -*-
"""NoneCap-backed hCaptcha agent.

Drop-in replacement for hcaptcha-challenger's AgentV at the call sites the
app already uses: callers construct the agent with a page and await
``wait_for_challenge()`` for a ChallengeSignal. Instead of solving the
challenge interactively with an LLM, this agent:

- waits for an hCaptcha challenge to become visible on the page,
- buys a solved token from NoneCap and injects it into the page,
- treats a widget-issued response token (invisible hCaptcha auto-pass) as a
  success, mirroring the old agent's response-queue behavior.

There is deliberately no interactive or LLM fallback: without a NoneCap API
key a visible challenge cannot be solved and the wait reports FAILURE.
"""

import time
from contextlib import suppress
from enum import Enum
from typing import Awaitable, Callable

from loguru import logger
from playwright.async_api import Page

from extensions.nonecap_solver import (
    deliver_hcaptcha_token,
    extract_hcaptcha_params,
    fetch_nonecap_token,
)


class ChallengeSignal(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    START = "start"
    RETRY = "retry"
    QR_DATA_NOT_FOUND = "qr_data_not_found"
    EXECUTION_TIMEOUT = "challenge_execution_timeout"
    RESPONSE_TIMEOUT = "challenge_response_timeout"


class CaptchaAgent:
    def __init__(
        self,
        page: Page,
        agent_config=None,
        *,
        after_inject: Callable[[], Awaitable[bool]] | None = None,
    ):
        self.page = page
        self.config = agent_config
        self._after_inject = after_inject

    async def _challenge_visible(self) -> bool:
        for frame in self.page.frames:
            if "hcaptcha" not in (frame.url or "").lower():
                continue
            with suppress(Exception):
                frame_element = await frame.frame_element()
                visible = await frame_element.evaluate("""
                    (element) => {
                      const rect = element.getBoundingClientRect();
                      const style = window.getComputedStyle(element);
                      return rect.width > 0 && rect.height > 0 &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none' &&
                        style.opacity !== '0';
                    }
                    """)
                if visible:
                    return True
        return False

    async def _response_token(self) -> str | None:
        for frame in self.page.frames:
            with suppress(Exception):
                value = await frame.evaluate("""
                    () => {
                      const el = document.querySelector(
                        'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"]'
                      );
                      return el ? el.value : null;
                    }
                    """)
                if value:
                    return str(value)
        return None

    async def wait_for_challenge(self) -> ChallengeSignal:
        timeout = float(self.config.EXECUTION_TIMEOUT) + float(self.config.RESPONSE_TIMEOUT)
        deadline = time.monotonic() + timeout
        baseline_token = await self._response_token()

        while time.monotonic() < deadline:
            if await self._challenge_visible():
                return await self._solve_visible_challenge(deadline, baseline_token)

            token = await self._response_token()
            if token and token != baseline_token:
                logger.success("hCaptcha passed without interaction (widget-issued token)")
                return ChallengeSignal.SUCCESS

            await self.page.wait_for_timeout(500)

        logger.error("Challenge execution timed out | timeout={}s", timeout)
        return ChallengeSignal.EXECUTION_TIMEOUT

    async def _solve_visible_challenge(
        self, deadline: float, baseline_token: str | None
    ) -> ChallengeSignal:
        if self.config.NONECAP_API_KEY is None:
            logger.error("Visible hCaptcha cannot be solved: NONECAP_API_KEY is not configured")
            while time.monotonic() < deadline:
                if not await self._challenge_visible():
                    token = await self._response_token()
                    if token and token != baseline_token:
                        return ChallengeSignal.SUCCESS
                    return ChallengeSignal.FAILURE
                await self.page.wait_for_timeout(500)
            return ChallengeSignal.FAILURE

        sitekey, rqdata = await extract_hcaptcha_params(self.page)
        if not sitekey:
            logger.warning("NoneCap solve skipped: no hCaptcha sitekey found on page")
            return ChallengeSignal.FAILURE

        user_agent = None
        with suppress(Exception):
            user_agent = await self.page.evaluate("() => navigator.userAgent")

        proxy = None
        proxy_secret = getattr(self.config, "NONECAP_PROXY", None)
        if proxy_secret is not None:
            proxy = proxy_secret.get_secret_value().strip() or None

        remaining = deadline - time.monotonic()
        token = await fetch_nonecap_token(
            api_key=self.config.NONECAP_API_KEY.get_secret_value(),
            sitekey=sitekey,
            page_url=self.page.url,
            rqdata=rqdata,
            user_agent=user_agent,
            timeout_seconds=min(
                float(self.config.NONECAP_TIMEOUT_SECONDS), max(10.0, remaining - 20.0)
            ),
            proxy=proxy,
        )
        if not token:
            return ChallengeSignal.FAILURE

        fields, callback_kind = await deliver_hcaptcha_token(self.page, token)
        if not fields and callback_kind is None:
            logger.warning("NoneCap solve failed: no response field or callback on page")
            return ChallengeSignal.FAILURE

        if callback_kind is not None:
            # The token reached the app through its own verify handler, which
            # owns submission from here — clicking sign-in again could reset
            # the flow. Give the widget a short grace period to close, then
            # report success either way and let the caller's outcome watcher
            # judge whether the app actually proceeded.
            logger.success("NoneCap token delivered via page callback | via={}", callback_kind)
            grace_deadline = min(deadline, time.monotonic() + 10.0)
            while time.monotonic() < grace_deadline:
                if not await self._challenge_visible():
                    logger.success("NoneCap token solve cleared the hCaptcha challenge")
                    return ChallengeSignal.SUCCESS
                await self.page.wait_for_timeout(500)
            logger.info(
                "Challenge still visible after callback delivery; "
                "deferring to the caller's outcome watcher"
            )
            return ChallengeSignal.SUCCESS

        if self._after_inject is not None:
            with suppress(Exception):
                await self._after_inject()

        verify_deadline = min(deadline, time.monotonic() + 20.0)
        while time.monotonic() < verify_deadline:
            if not await self._challenge_visible():
                logger.success("NoneCap token solve cleared the hCaptcha challenge")
                return ChallengeSignal.SUCCESS
            await self.page.wait_for_timeout(500)

        logger.warning("NoneCap token injected but the challenge is still visible")
        return ChallengeSignal.FAILURE
