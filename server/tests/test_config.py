"""运行配置：开发默认值安全，生产环境拒绝带着危险配置启动。"""

from __future__ import annotations

import pytest
from app.core.config import DEV_CRYPTO_KEY, Settings
from pydantic import ValidationError

PRODUCTION = {
    "environment": "production",
    "database_url": "postgresql+pg8000://kg@db/knowledge",
    "crypto_key": "k" * 44,
    "create_tables_on_startup": False,
}


def test_development_defaults_do_not_expose_reset_tokens_or_trust_proxies() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.expose_reset_token is False
    assert settings.trusted_proxy_count == 0


def test_production_accepts_explicit_safe_configuration() -> None:
    assert Settings(_env_file=None, **PRODUCTION).environment == "production"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"database_url": "sqlite:///./knowledge.db"}, "PostgreSQL"),
        ({"crypto_key": DEV_CRYPTO_KEY}, "KG_CRYPTO_KEY"),
        ({"crypto_key": "too-short"}, "KG_CRYPTO_KEY"),
        ({"create_tables_on_startup": True}, "KG_CREATE_TABLES_ON_STARTUP"),
        ({"expose_reset_token": True}, "reset tokens"),
    ],
)
def test_production_rejects_unsafe_configuration(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **{**PRODUCTION, **override})


def test_environment_variables_drive_the_production_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KG_ENVIRONMENT", "production")
    monkeypatch.setenv("KG_DATABASE_URL", PRODUCTION["database_url"])
    monkeypatch.setenv("KG_CRYPTO_KEY", DEV_CRYPTO_KEY)
    monkeypatch.setenv("KG_CREATE_TABLES_ON_STARTUP", "false")
    with pytest.raises(ValidationError, match="KG_CRYPTO_KEY"):
        Settings(_env_file=None)
