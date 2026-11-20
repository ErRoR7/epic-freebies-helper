# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"


def _load_wxpush_module():
    # The module under test must only import httpx/loguru and
    # services.epic_collection_summary_service. Do NOT let it grow imports of
    # services.telegram_notification_service / services.epic_games_service —
    # the stub list below would then need to be extended in lockstep.
    stub_names = ("httpx", "loguru", "services", "services.epic_collection_summary_service")
    saved = {name: sys.modules.get(name) for name in stub_names}

    for name in stub_names:
        sys.modules[name] = types.ModuleType(name)

    log_mod = sys.modules["loguru"]

    class _Logger:
        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

        def success(self, *args, **kwargs):
            return None

        def debug(self, *args, **kwargs):
            return None

        def catch(self, *args, **kwargs):
            def decorator(fn):
                return fn

            if args and callable(args[0]) and not kwargs:
                return args[0]
            return decorator

    log_mod.logger = _Logger()

    summary_mod = sys.modules["services.epic_collection_summary_service"]

    class CollectionSummary:
        def __init__(
            self,
            all_promotions=None,
            newly_claimed_promotions=None,
            previously_claimed_promotions=None,
            unconfirmed_promotions=None,
            failed_promotions=None,
            error_message="",
        ):
            self.all_promotions = all_promotions or []
            self.newly_claimed_promotions = newly_claimed_promotions or []
            self.previously_claimed_promotions = previously_claimed_promotions or []
            self.unconfirmed_promotions = unconfirmed_promotions or []
            self.failed_promotions = failed_promotions or []
            self.error_message = error_message

    summary_mod.CollectionSummary = CollectionSummary

    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))

    services_pkg = sys.modules["services"]
    services_pkg.epic_collection_summary_service = summary_mod

    try:
        spec = importlib.util.spec_from_file_location(
            "wxpush_notification_service_under_test",
            APP_DIR / "services" / "wxpush_notification_service.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        return module, CollectionSummary
    finally:
        # Restore immediately so later test collection is not polluted.
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


wxpush, CollectionSummary = _load_wxpush_module()


def _game(title="Demo Game"):
    return SimpleNamespace(title=title, url="https://store.epicgames.com/en-US/p/demo")


def _summary(all_count=0, newly=0, previously=0, unconfirmed=0, failed=0, error=""):
    def build(count, title):
        return [_game(title=f"{title} {i}") for i in range(count)]

    return CollectionSummary(
        all_promotions=build(all_count, "all"),
        newly_claimed_promotions=build(newly, "new"),
        previously_claimed_promotions=build(previously, "prev"),
        unconfirmed_promotions=build(unconfirmed, "unconf"),
        failed_promotions=build(failed, "fail"),
        error_message=error,
    )


def test_title_all_claimed_shape():
    assert wxpush.build_wxpush_title(_summary(all_count=7, newly=2)) == "Epic:new2/7 total"


def test_title_all_owned_already_shape():
    assert (
        wxpush.build_wxpush_title(_summary(all_count=7, previously=7))
        == "Epic:owned/7 total"
    )


def test_title_empty_week_shape():
    assert wxpush.build_wxpush_title(_summary()) == "Epic:0 total"


def test_title_partial_failure_shape():
    assert (
        wxpush.build_wxpush_title(_summary(all_count=7, newly=2, failed=1, error="boom"))
        == "Epic:new2 fail1"
    )


def test_title_partial_without_counts_shape():
    assert (
        wxpush.build_wxpush_title(_summary(all_count=7, newly=2, error="boom"))
        == "Epic:new2 partial"
    )


def test_title_needs_confirmation_shape():
    assert (
        wxpush.build_wxpush_title(_summary(all_count=7, newly=2, unconfirmed=1))
        == "Epic:new2 pending1"
    )


def test_title_total_failure_shape():
    assert (
        wxpush.build_wxpush_title(_summary(all_count=3, error="boom")) == "Epic failed:boom"
    )


def test_title_failure_uses_first_error_line():
    title = wxpush.build_wxpush_title(_summary(all_count=3, error="First line\n\nSecond line"))
    assert title == "Epic failed:First li"


def test_title_is_single_line_and_hard_clipped():
    cases = [
        _summary(all_count=7, newly=2),
        _summary(all_count=7, newly=2, failed=1, error="boom"),
        _summary(all_count=7, newly=2, unconfirmed=1),
        _summary(all_count=999, newly=99, failed=9, unconfirmed=9),
        _summary(all_count=3, error="boom" * 30),
    ]
    for summary in cases:
        title = wxpush.build_wxpush_title(summary)
        assert "\n" not in title
        assert len(title) <= wxpush.TITLE_FIELD_MAX_CHARS


def test_content_single_account_omits_account_label_by_default():
    content = wxpush.build_wxpush_content(_summary(all_count=7, newly=2))
    assert "Account: " not in content
    assert "Status: Success" in content
    assert "This week's games:" in content
    assert "Newly claimed:" in content
    assert "Previously claimed:\nNone" in content


def test_content_multi_account_includes_masked_account_label():
    content = wxpush.build_wxpush_content(
        _summary(all_count=7, newly=2), account_label="ab***@example.com"
    )
    assert "Account: ab***@example.com" in content
    assert content.index("Account: ") < content.index("Status: ")


def test_content_lists_game_titles():
    summary = _summary(all_count=2, newly=1)
    summary.all_promotions = [_game("It Takes Two"), _game("Diablo IV")]
    summary.newly_claimed_promotions = [_game("Diablo IV")]
    content = wxpush.build_wxpush_content(summary)
    assert "- It Takes Two" in content
    assert "- Diablo IV" in content


def test_content_conditional_sections_and_error_reason():
    content = wxpush.build_wxpush_content(
        _summary(all_count=5, newly=1, unconfirmed=1, failed=1, error="boom")
    )
    assert "Unconfirmed:" in content
    assert "Failed to claim:" in content
    assert "Failure reason: boom" in content


def test_content_truncates_at_safe_size():
    content = wxpush.build_wxpush_content(_summary(all_count=300, newly=200))
    assert content.endswith("...(truncated)")
    assert len(content) <= wxpush.CONTENT_MAX_CHARS


def test_enabled_requires_token_and_valid_endpoint(monkeypatch):
    monkeypatch.delenv("WXPUSH_ENDPOINT", raising=False)
    monkeypatch.delenv("WXPUSH_TOKEN", raising=False)
    assert wxpush.wxpush_notifications_enabled() is False

    monkeypatch.setenv("WXPUSH_TOKEN", "secret")
    assert wxpush.wxpush_notifications_enabled() is False

    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://wx.example.workers.dev")
    assert wxpush.wxpush_notifications_enabled() is True


def test_enabled_rejects_endpoint_without_scheme(monkeypatch):
    monkeypatch.delenv("WXPUSH_ENDPOINT", raising=False)
    monkeypatch.delenv("WXPUSH_TOKEN", raising=False)
    monkeypatch.setenv("WXPUSH_TOKEN", "secret")
    monkeypatch.setenv("WXPUSH_ENDPOINT", "wx.example.workers.dev")
    assert wxpush.wxpush_notifications_enabled() is False


def test_enabled_rejects_malformed_endpoint(monkeypatch):
    # A malformed URL must disable the channel instead of raising later at
    # delivery time (regression: urlsplit used to explode outside the try).
    monkeypatch.delenv("WXPUSH_ENDPOINT", raising=False)
    monkeypatch.delenv("WXPUSH_TOKEN", raising=False)
    monkeypatch.setenv("WXPUSH_TOKEN", "secret")
    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://[broken")
    assert wxpush.wxpush_notifications_enabled() is False


def test_send_with_malformed_endpoint_skips_without_raising(monkeypatch):
    monkeypatch.delenv("WXPUSH_ENDPOINT", raising=False)
    monkeypatch.delenv("WXPUSH_TOKEN", raising=False)
    monkeypatch.setenv("WXPUSH_TOKEN", "secret")
    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://[broken")
    # Invalid endpoint means the channel is off; the call must be a silent
    # no-op and never surface a configuration error into the claim task.
    assert asyncio.run(wxpush.send_collection_summary_to_wxpush(_summary(all_count=1))) is None


def test_normalize_endpoint_appends_wxsend(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://wx.example.workers.dev")
    assert wxpush._normalize_wxsend_endpoint() == "https://wx.example.workers.dev/wxsend"


def test_normalize_endpoint_keeps_explicit_wxsend(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://wx.example.workers.dev/wxsend")
    assert wxpush._normalize_wxsend_endpoint() == "https://wx.example.workers.dev/wxsend"


def test_normalize_endpoint_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://wx.example.workers.dev/")
    assert wxpush._normalize_wxsend_endpoint() == "https://wx.example.workers.dev/wxsend"


def test_normalize_endpoint_rejects_schemeless(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "localhost:3939")
    assert wxpush._normalize_wxsend_endpoint() == ""


def test_normalize_endpoint_rejects_malformed_brackets(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://[broken")
    assert wxpush._normalize_wxsend_endpoint() == ""


def test_normalize_endpoint_rejects_unsupported_scheme(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "ftp://wx.example.workers.dev")
    assert wxpush._normalize_wxsend_endpoint() == ""


def test_normalize_endpoint_rejects_missing_netloc(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://")
    assert wxpush._normalize_wxsend_endpoint() == ""


def test_success_message_confirms_delivery_protocol():
    ok = "Successfully sent messages to 1 user(s). First response: ok"
    assert wxpush._success_message(f'{{"msg": "{ok}"}}') == ok


def test_success_message_rejects_non_wxpush_bodies():
    # A 200 HTML page (e.g. the /skin route) or any malformed body must not be
    # reported as a successful delivery.
    assert wxpush._success_message("<!doctype html><html>skin page</html>") is None
    assert wxpush._success_message("not json at all") is None
    assert wxpush._success_message('{"msg": "ok"}') is None
    assert wxpush._success_message('{"errcode": 0}') is None
    assert wxpush._success_message("[]") is None
    assert wxpush._success_message("") is None


def test_default_skin_base_url(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "https://wx.example.workers.dev")
    assert wxpush._default_skin_base_url() == "https://wx.example.workers.dev/skin"


def test_default_skin_base_url_preserves_http_scheme(monkeypatch):
    monkeypatch.setenv("WXPUSH_ENDPOINT", "http://127.0.0.1:3939")
    assert wxpush._default_skin_base_url() == "http://127.0.0.1:3939/skin"
