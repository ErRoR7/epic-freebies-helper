# -*- coding: utf-8 -*-
import os
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- Core path definitions ---
PROJECT_ROOT = Path(__file__).parent
VOLUMES_DIR = PROJECT_ROOT.joinpath("volumes")
LOG_DIR = VOLUMES_DIR.joinpath("logs")
USER_DATA_DIR = VOLUMES_DIR.joinpath("user_data")
RUNTIME_DIR = VOLUMES_DIR.joinpath("runtime")
SCREENSHOTS_DIR = VOLUMES_DIR.joinpath("screenshots")
RECORD_DIR = VOLUMES_DIR.joinpath("record")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


# === Settings class ===
class EpicSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    EPIC_ACCOUNTS: SecretStr | None = Field(
        default=None, description="Optional multiline email:password account list"
    )
    EPIC_EMAIL: str = Field(default_factory=lambda: _env("EPIC_EMAIL", ""))
    EPIC_PASSWORD: SecretStr = Field(default_factory=lambda: _env("EPIC_PASSWORD", ""))

    BROWSER_BACKEND: str = Field(
        default="auto", description="Supported values: auto, camoufox, playwright"
    )
    BROWSER_PROXY: SecretStr | None = Field(
        default=None, description="Optional HTTP(S) or SOCKS proxy URL shared by browser backends."
    )

    # hCaptcha solving is token-based via NoneCap; there is no LLM solver.
    NONECAP_API_KEY: SecretStr | None = Field(
        default=None, description="NoneCap API key; required to solve hCaptcha challenges"
    )
    NONECAP_TIMEOUT_SECONDS: float = Field(default=110.0, gt=10.0, le=300.0)
    NONECAP_PROXY: SecretStr | None = Field(
        default=None,
        description="Optional proxy for NoneCap solves; set it to the same egress as "
        "BROWSER_PROXY so solved tokens originate from the browser session's IP",
    )

    # hCaptcha runtime limits, consumed by CaptchaAgent.wait_for_challenge.
    EXECUTION_TIMEOUT: float = Field(
        default=120.0, description="Max seconds to wait for a challenge to appear and be solved"
    )
    RESPONSE_TIMEOUT: float = Field(
        default=30.0, description="Extra grace seconds appended to the challenge wait"
    )

    ENABLE_APSCHEDULER: bool = Field(default=True)
    TASK_TIMEOUT_SECONDS: int = Field(default=900)
    AUTH_MAX_ATTEMPTS: int = Field(default=5, ge=3, le=8)
    REDIS_URL: str = Field(default="redis://redis:6379/0")
    CELERY_WORKER_CONCURRENCY: int = Field(default=1)
    CELERY_TASK_TIME_LIMIT: int = Field(default=1200)
    CELERY_TASK_SOFT_TIME_LIMIT: int = Field(default=900)

    @model_validator(mode="after")
    def _apply_runtime_defaults(self):
        for field_name in ("BROWSER_BACKEND", "EPIC_EMAIL"):
            value = getattr(self, field_name, None)
            if isinstance(value, str):
                setattr(self, field_name, value.strip())
        self.BROWSER_BACKEND = (self.BROWSER_BACKEND or "").lower() or "auto"
        return self

    @property
    def captcha_configuration_error(self) -> str | None:
        if self.NONECAP_API_KEY is None:
            return (
                "Invalid captcha configuration: NONECAP_API_KEY is empty. "
                "Set NONECAP_API_KEY in GitHub Actions Secrets so hCaptcha "
                "challenges can be solved via NoneCap."
            )
        return None

    @property
    def user_data_dir(self) -> Path:
        target_ = self.user_data_dir_for("camoufox")
        return target_

    def user_data_dir_for(self, backend: str) -> Path:
        backend = (backend or "camoufox").strip().lower()
        suffix = f".{backend}"
        target_ = USER_DATA_DIR.joinpath(f"{self.EPIC_EMAIL}{suffix}")
        target_.mkdir(parents=True, exist_ok=True)
        return target_


settings = EpicSettings()
