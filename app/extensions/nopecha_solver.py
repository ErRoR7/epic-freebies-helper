# -*- coding: utf-8 -*-
"""NopeCHA token-based hCaptcha solving for the Epic login flow.

When a NOPECHA_API_KEY is configured, the authorization service can try this
route before the interactive hcaptcha-challenger agent: read the sitekey (and
enterprise rqdata, when present) from the live hCaptcha frame, buy a solved
token from NopeCHA, and inject it into the page's h-captcha-response fields.
Epic's own form submission then verifies the token server-side, which bypasses
the interactive solver's checkcaptcha result pairing entirely.

Every failure path returns None/False so callers can fall back to the
interactive solver unchanged. The full token is never logged.
"""
import asyncio
from urllib.parse import parse_qs, urlparse

import httpx
from loguru import logger
from playwright.async_api import Page

NOPECHA_TOKEN_URL = "https://api.nopecha.com/v1/token/hcaptcha"

# A solved hCaptcha token is a long P0/passcode string (hundreds of chars);
# a job id returned by the submit call is short. Length separates the two.
_TOKEN_MIN_LENGTH = 200


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
        dom_params = await page.evaluate(
            """
            () => {
              const el = document.querySelector('[data-sitekey]');
              if (!el) return null;
              return {
                sitekey: el.getAttribute('data-sitekey'),
                rqdata: el.getAttribute('data-rqdata'),
              };
            }
            """
        )
    except Exception:
        dom_params = None
    if dom_params and dom_params.get("sitekey"):
        return dom_params["sitekey"], dom_params.get("rqdata")
    return None, None


async def fetch_nopecha_token(
    *,
    api_key: str,
    sitekey: str,
    page_url: str,
    rqdata: str | None,
    timeout_seconds: float,
) -> str | None:
    """Submit an hCaptcha token job to NopeCHA and poll until it resolves."""
    payload: dict = {"key": api_key, "sitekey": sitekey, "url": page_url}
    if rqdata:
        payload["data"] = {"rqdata": rqdata}

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        try:
            response = await client.post(NOPECHA_TOKEN_URL, json=payload)
            body = response.json()
        except Exception as err:
            logger.warning("NopeCHA token submit failed | err={!r}", err)
            return None

        job_id = body.get("data") if isinstance(body, dict) else None
        if not job_id or not isinstance(job_id, str):
            logger.warning(
                "NopeCHA token submit returned no job id | status={} | body={}",
                response.status_code,
                str(body)[:300],
            )
            return None
        if len(job_id) > _TOKEN_MIN_LENGTH:
            logger.info("NopeCHA returned a token synchronously | len={}", len(job_id))
            return job_id
        logger.info("NopeCHA token job submitted | job_id={}", job_id)

        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(5)
            try:
                response = await client.get(
                    NOPECHA_TOKEN_URL, params={"key": api_key, "id": job_id}
                )
                body = response.json()
            except Exception as err:
                logger.warning("NopeCHA token poll failed | err={!r}", err)
                continue

            data = body.get("data") if isinstance(body, dict) else None
            if isinstance(data, str) and len(data) > _TOKEN_MIN_LENGTH:
                logger.info("NopeCHA token solved | len={}", len(data))
                return data

            message = str(body.get("message") or "") if isinstance(body, dict) else ""
            if any(
                marker in message.lower()
                for marker in ("invalid", "not found", "discontinued", "banned", "insufficient")
            ):
                logger.warning("NopeCHA token job failed terminally | body={}", str(body)[:300])
                return None
            logger.debug("NopeCHA token job still pending | body={}", str(body)[:200])

    logger.warning("NopeCHA token job timed out after {}s", timeout_seconds)
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
        logger.warning("NopeCHA token injection failed | err={!r}", err)
        return 0
    logger.info("NopeCHA token injected into {} response field(s)", count)
    return int(count or 0)
