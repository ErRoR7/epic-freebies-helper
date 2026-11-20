# -*- coding: utf-8 -*-
"""NoneCap token-based hCaptcha solving for the Epic flows.

When a NONECAP_API_KEY is configured, the captcha agent can clear a visible
hCaptcha without interacting with it: read the sitekey (and enterprise
rqdata, when present) from the live hCaptcha frame, buy a solved token from
NoneCap, and inject it into the page's h-captcha-response fields. Epic's own
form submission then verifies the token server-side.

Epic's hCaptcha deployment is the enterprise variant, so solves are
submitted as ``hcaptcha_enterprise`` (rqdata is optional and only sent when
the page supplies one). Failed solves are not charged by NoneCap.

Every failure path returns None/False so callers can treat the attempt as a
failed solve and move on. The full token is never logged.
"""

import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
from loguru import logger
from playwright.async_api import Page

NONECAP_SOLVES_URL = "https://api.nonecap.com/v1/solves"

_TERMINAL_FAILURE_STATUSES = {"failed", "cancelled", "expired"}


async def extract_hcaptcha_params(page: Page) -> tuple[str | None, str | None]:
    """Return (sitekey, rqdata) for the hCaptcha widget currently on the page."""
    for frame in page.frames:
        url = frame.url or ""
        if "hcaptcha" not in url.lower():
            continue
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        for pair in parsed.fragment.split("&"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                params.setdefault(key, []).append(value)
        sitekey = (params.get("sitekey") or [None])[0]
        rqdata = (params.get("rqdata") or [None])[0]
        if sitekey:
            return sitekey, rqdata

    # Fallback: widget configuration rendered into the DOM.
    try:
        dom_params = await page.evaluate("""
            () => {
              const el = document.querySelector('[data-sitekey]');
              if (!el) return null;
              return {
                sitekey: el.getAttribute('data-sitekey'),
                rqdata: el.getAttribute('data-rqdata'),
              };
            }
            """)
    except Exception:
        dom_params = None
    if dom_params and dom_params.get("sitekey"):
        return dom_params["sitekey"], dom_params.get("rqdata")
    return None, None


def _error_summary(body: object) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return f"code={error.get('code')} message={error.get('message')}"
    return str(body)[:200]


async def fetch_nonecap_token(
    *,
    api_key: str,
    sitekey: str,
    page_url: str,
    rqdata: str | None,
    user_agent: str | None,
    timeout_seconds: float,
) -> str | None:
    """Submit an hCaptcha solve to NoneCap and long-poll until it resolves."""
    payload: dict = {"type": "hcaptcha_enterprise", "sitekey": sitekey, "url": page_url}
    if rqdata:
        payload["rqdata"] = rqdata
    if user_agent:
        payload["user_agent"] = user_agent

    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    async with httpx.AsyncClient(timeout=httpx.Timeout(100.0)) as client:
        try:
            response = await client.post(
                NONECAP_SOLVES_URL, params={"wait": 90}, headers=headers, json=payload
            )
            solve = response.json()
        except Exception as err:
            logger.warning("NoneCap solve submit failed | err={!r}", err)
            return None

        if response.status_code not in (200, 202):
            logger.warning(
                "NoneCap solve submit refused | status={} | {}",
                response.status_code,
                _error_summary(solve),
            )
            return None

        solve_id = solve.get("id") if isinstance(solve, dict) else None
        logger.info("NoneCap solve submitted | solve_id={}", solve_id)

        while True:
            if isinstance(solve, dict):
                token = solve.get("token")
                if token:
                    logger.info(
                        "NoneCap solve succeeded | solve_id={} | token_len={}",
                        solve_id,
                        len(str(token)),
                    )
                    return str(token)

                status = str(solve.get("status") or "")
                if status in _TERMINAL_FAILURE_STATUSES:
                    error = solve.get("error") or {}
                    logger.warning(
                        "NoneCap solve {} | solve_id={} | code={} | reason={}",
                        status,
                        solve_id,
                        error.get("code"),
                        error.get("reason"),
                    )
                    return None

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0 or not solve_id:
                logger.warning("NoneCap solve timed out after {}s", timeout_seconds)
                return None

            try:
                response = await client.get(
                    f"{NONECAP_SOLVES_URL}/{solve_id}",
                    params={"wait": max(1, min(90, int(remaining)))},
                    headers=headers,
                )
                solve = response.json()
            except Exception as err:
                logger.warning("NoneCap solve poll failed | err={!r}", err)
                return None

            if response.status_code not in (200, 202):
                logger.warning(
                    "NoneCap solve poll refused | status={} | {}",
                    response.status_code,
                    _error_summary(solve),
                )
                return None


async def inject_hcaptcha_token(page: Page, token: str) -> int:
    """Write the token into every h-captcha-response field on the page.

    Returns the number of fields populated (0 means the page exposes no
    response field to inject into).
    """
    try:
        count = await page.evaluate(
            """
            (token) => {
              const fields = document.querySelectorAll(
                'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"]'
              );
              let populated = 0;
              fields.forEach((el) => {
                el.value = token;
                el.innerHTML = token;
                populated += 1;
              });
              return populated;
            }
            """,
            token,
        )
    except Exception as err:
        logger.warning("NoneCap token injection failed | err={!r}", err)
        return 0
    logger.info("NoneCap token injected into {} response field(s)", count)
    return int(count or 0)
