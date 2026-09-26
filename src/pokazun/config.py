"""Runtime configuration. Every value comes from environment variables with the POKAZUN_ prefix."""

import re
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pokazun.catalog.airtable import AIRTABLE_API_URL

WEBHOOK_PATH = "/tg/webhook"
_SECRET_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")


def _parse_ids(raw: str) -> frozenset[int]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        return frozenset(int(p) for p in parts)
    except ValueError as exc:
        raise ValueError("POKAZUN_ALLOWED_USER_IDS must be comma-separated integers") from exc


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POKAZUN_", extra="ignore")

    env: Literal["prod", "staging", "dev"]
    bot_token: SecretStr
    database_url: SecretStr
    telegram_mode: Literal["webhook", "polling"] = "webhook"
    public_base_url: str = ""
    webhook_secret: SecretStr | None = None
    alert_chat_id: int | None = None
    allowed_user_ids: str = ""
    log_level: str = "INFO"
    log_dir: Path | None = None
    state_dir: Path = Path("/var/lib/pokazun")
    backup_marker_path: Path = Path("/backups/last_backup_at")
    web_host: str = "0.0.0.0"  # noqa: S104 — container-internal bind, the proxy is the only entrypoint
    web_port: int = 8080
    airtable_token: SecretStr | None = None
    airtable_base_id: str = "appLx30Y68Qy0I9Au"
    airtable_table_id: str = "tblgO046VTYnqOgZa"
    airtable_api_url: str = AIRTABLE_API_URL
    sync_interval_s: int = 300
    full_sync_interval_h: int = 24

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        allowlist = _parse_ids(self.allowed_user_ids)
        if self.telegram_mode == "webhook":
            if not self.public_base_url.startswith("https://"):
                raise ValueError("POKAZUN_PUBLIC_BASE_URL must be an https:// URL in webhook mode")
            secret = self.webhook_secret.get_secret_value() if self.webhook_secret else ""
            if not _SECRET_TOKEN_RE.match(secret):
                raise ValueError(
                    "POKAZUN_WEBHOOK_SECRET must be 16-256 chars of A-Z, a-z, 0-9, _ or -"
                )
        if self.env == "staging" and not allowlist:
            raise ValueError("staging requires POKAZUN_ALLOWED_USER_IDS")
        if self.env == "prod":
            if allowlist:
                raise ValueError("prod must not set POKAZUN_ALLOWED_USER_IDS")
            if self.alert_chat_id is None:
                raise ValueError("prod requires POKAZUN_ALERT_CHAT_ID")
            if self.telegram_mode != "webhook":
                raise ValueError("prod must run in webhook mode")
        if self.env in ("prod", "staging") and self.airtable_token is None:
            raise ValueError(f"{self.env} requires POKAZUN_AIRTABLE_TOKEN")
        return self

    @property
    def allowlist(self) -> frozenset[int]:
        return _parse_ids(self.allowed_user_ids)

    @property
    def webhook_url(self) -> str:
        return self.public_base_url.rstrip("/") + WEBHOOK_PATH
