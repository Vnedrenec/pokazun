import pytest
from pydantic import ValidationError

from pokazun.config import WEBHOOK_PATH, Settings

BASE = {
    "bot_token": "123456:" + "A" * 35,
    "database_url": "postgresql+asyncpg://u:p@db/pokazun",
    "public_base_url": "https://bot.praktik.cn.ua",
    "webhook_secret": "s" * 32,
}


def make(**overrides) -> Settings:
    return Settings(**{**BASE, **overrides})


def test_prod_valid():
    s = make(env="prod", alert_chat_id=-100123)
    assert s.allowlist == frozenset()
    assert s.webhook_url == "https://bot.praktik.cn.ua" + WEBHOOK_PATH


def test_prod_requires_alert_chat():
    with pytest.raises(ValidationError, match="ALERT_CHAT_ID"):
        make(env="prod")


def test_prod_rejects_allowlist():
    with pytest.raises(ValidationError, match="must not set"):
        make(env="prod", alert_chat_id=-1, allowed_user_ids="1")


def test_prod_rejects_polling():
    with pytest.raises(ValidationError, match="webhook mode"):
        make(env="prod", alert_chat_id=-1, telegram_mode="polling")


def test_staging_requires_allowlist():
    with pytest.raises(ValidationError, match="ALLOWED_USER_IDS"):
        make(env="staging", alert_chat_id=-1)


def test_allowlist_parsing():
    s = make(env="staging", allowed_user_ids=" 11, 22,33 ")
    assert s.allowlist == frozenset({11, 22, 33})


def test_allowlist_rejects_garbage():
    with pytest.raises(ValidationError, match="integers"):
        make(env="staging", allowed_user_ids="11,abc")


def test_webhook_requires_https():
    with pytest.raises(ValidationError, match="https"):
        make(env="dev", public_base_url="http://bot.praktik.cn.ua")


def test_webhook_secret_format():
    with pytest.raises(ValidationError, match="WEBHOOK_SECRET"):
        make(env="dev", webhook_secret="short")


def test_polling_dev_needs_no_webhook_fields():
    s = Settings(
        env="dev",
        bot_token=BASE["bot_token"],
        database_url=BASE["database_url"],
        telegram_mode="polling",
    )
    assert s.telegram_mode == "polling"


def test_secrets_not_in_repr():
    s = make(env="prod", alert_chat_id=-1)
    assert BASE["bot_token"] not in repr(s)
    assert "u:p@" not in repr(s)


def test_loads_from_env(monkeypatch):
    monkeypatch.setenv("POKAZUN_ENV", "staging")
    monkeypatch.setenv("POKAZUN_BOT_TOKEN", BASE["bot_token"])
    monkeypatch.setenv("POKAZUN_DATABASE_URL", BASE["database_url"])
    monkeypatch.setenv("POKAZUN_TELEGRAM_MODE", "polling")
    monkeypatch.setenv("POKAZUN_ALLOWED_USER_IDS", "7")
    assert Settings().allowlist == frozenset({7})
