# -*- coding: utf-8 -*-
"""NoneCap token-based hCaptcha solving for the Epic flows.

When a NONECAP_API_KEY is configured, the captcha agent can clear a visible
hCaptcha without interacting with it: read the sitekey (and enterprise
rqdata, when present) from the live hCaptcha frame, buy a solved token from
NoneCap, and deliver it to the page — into the h-captcha-response fields AND
through the widget's own verify callback, which is what framework-driven
forms (Epic's React login included) actually listen to.

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
    proxy: str | None = None,
) -> str | None:
    """Submit an hCaptcha solve to NoneCap and long-poll until it resolves."""
    payload: dict = {"type": "hcaptcha_enterprise", "sitekey": sitekey, "url": page_url}
    if rqdata:
        payload["rqdata"] = rqdata
    if user_agent:
        payload["user_agent"] = user_agent
    if proxy:
        # Solve through the same egress the browser uses (pair with
        # BROWSER_PROXY) so the token's origin matches the session's.
        payload["proxy"] = proxy

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


async def deliver_hcaptcha_token(page: Page, token: str) -> tuple[int, str | None]:
    """Deliver a solved token to the page the way a real verification would.

    Writing the token into the h-captcha-response fields is not enough on
    framework-driven login forms (Epic's included): the app tracks captcha
    state through the widget's verify callback, so a bare field write leaves
    the app believing no verification happened — it re-opens the widget on
    submit and never posts the login. This therefore also hunts down the
    page's verify callback and invokes it with the token, in order:

    1. an explicit ``data-callback`` global named on the widget element,
    2. a React ``onVerify`` prop on the widget component (fiber walk),
    3. a callback registered in the hCaptcha API's internal client table.

    Returns (fields_populated, callback_kind) where callback_kind is None
    when no callback could be invoked.
    """
    try:
        result = await page.evaluate(
            """
            (token) => {
              const result = { fields: 0, callback: null, detail: '' };
              const note = (msg) => { result.detail = (result.detail + ' ' + msg).trim(); };

              // 1) Populate the response fields via the native setter and
              //    real events, so framework value tracking notices.
              const setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
              );
              document.querySelectorAll(
                'textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"]'
              ).forEach((el) => {
                try {
                  if (setter && setter.set) setter.set.call(el, token);
                  else el.value = token;
                  el.dispatchEvent(new Event('input', { bubbles: true }));
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                  result.fields += 1;
                } catch (e) { note('field:' + e); }
              });

              const iframe = document.querySelector('iframe[data-hcaptcha-widget-id]');
              const sitekeyEl = document.querySelector('[data-sitekey]');
              const anchor = (iframe && (iframe.closest('div') || iframe.parentElement))
                || sitekeyEl || (iframe && iframe.parentElement) || null;

              // 2) Explicit data-callback global.
              const cbHost = document.querySelector('[data-callback]') || anchor;
              const cbName = cbHost && cbHost.getAttribute
                ? cbHost.getAttribute('data-callback') : null;
              if (cbName && typeof window[cbName] === 'function') {
                try {
                  window[cbName](token);
                  result.callback = 'data-callback';
                  return result;
                } catch (e) { note('data-callback:' + e); }
              }

              // 3) React fiber walk looking for an onVerify prop.
              const startNodes = [];
              if (anchor) startNodes.push(anchor);
              if (iframe && iframe.parentElement) startNodes.push(iframe.parentElement);
              if (sitekeyEl) startNodes.push(sitekeyEl);
              for (const node of startNodes) {
                const fiberKey = Object.keys(node).find(
                  (k) => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$')
                );
                if (!fiberKey) continue;
                let fiber = node[fiberKey];
                let hops = 0;
                while (fiber && hops < 40) {
                  const props = fiber.memoizedProps || fiber.pendingProps;
                  if (props && typeof props.onVerify === 'function') {
                    try {
                      props.onVerify(token);
                      result.callback = 'react-onVerify';
                      return result;
                    } catch (e) { note('onVerify:' + e); break; }
                  }
                  const sn = fiber.stateNode;
                  if (sn && typeof sn === 'object' && sn.props
                      && typeof sn.props.onVerify === 'function') {
                    try {
                      sn.props.onVerify(token);
                      result.callback = 'react-onVerify';
                      return result;
                    } catch (e) { note('stateNode-onVerify:' + e); break; }
                  }
                  fiber = fiber.return;
                  hops += 1;
                }
              }

              // 4) hCaptcha API internal client registry (best effort).
              try {
                const hc = window.hcaptcha;
                if (hc) {
                  const seen = new Set();
                  const queue = [[hc, 0]];
                  while (queue.length) {
                    const [obj, depth] = queue.shift();
                    if (!obj || typeof obj !== 'object' || seen.has(obj) || depth > 3) continue;
                    seen.add(obj);
                    for (const key of Object.keys(obj)) {
                      let val;
                      try { val = obj[key]; } catch (e) { continue; }
                      if (val && typeof val === 'object') {
                        if (typeof val.callback === 'function' && ('sitekey' in val)) {
                          try {
                            val.callback(token);
                            result.callback = 'hcaptcha-internal';
                            return result;
                          } catch (e) { note('internal:' + e); }
                        }
                        queue.push([val, depth + 1]);
                      }
                    }
                  }
                }
              } catch (e) { note('hcaptcha-scan:' + e); }

              return result;
            }
            """,
            token,
        )
    except Exception as err:
        logger.warning("NoneCap token delivery failed | err={!r}", err)
        return 0, None

    fields = int((result or {}).get("fields") or 0)
    callback = (result or {}).get("callback")
    detail = str((result or {}).get("detail") or "")
    logger.info(
        "NoneCap token delivered | fields={} | callback={}{}",
        fields,
        callback,
        f" | detail={detail}" if detail else "",
    )
    return fields, callback


async def inject_hcaptcha_token(page: Page, token: str) -> int:
    """Backward-compatible wrapper: deliver the token, return field count."""
    fields, _callback = await deliver_hcaptcha_token(page, token)
    return fields
