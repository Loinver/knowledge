"""应用配置（pydantic-settings）。

开发态默认 SQLite（单文件、零依赖），生产用 PostgreSQL。
元数据库与被抽取的源库物理分离——这是硬约束。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_CRYPTO_KEY = "dev-only-do-not-use-in-production-key-32bytes!"


class Settings(BaseSettings):
    """运行期配置，从环境变量读取，缺省值面向开发态。

    生产部署用 PostgreSQL，开发用 SQLite；两者通过 DATABASE_URL 切换。
    凭据加密密钥生产必须显式提供，开发缺省为固定值（仅本地）。
    """

    model_config = SettingsConfigDict(
        env_prefix="KG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "production"] = "development"
    database_url: str = "sqlite:///./knowledge.db"
    crypto_key: str = DEV_CRYPTO_KEY
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    # 本地开发自动建表；使用 Alembic 管理结构的环境应显式关闭。
    create_tables_on_startup: bool = True

    # --- 账号模块 ---
    # 公开注册默认关闭：账号由管理员在用户管理里创建，首个管理员用
    # `make seed-admin` 生成（见 docs/adr/0002-account-auth.md）。
    allow_public_registration: bool = False
    # 没有邮件服务时默认关闭找回功能；本地联调须显式开启。
    expose_reset_token: bool = False
    # 令牌有效期：访问令牌短、刷新令牌长；重置令牌只够走完一次改密。
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 1_209_600
    reset_token_ttl_seconds: int = 3600
    # 口令派生迭代次数。默认值按 OWASP 对 PBKDF2-HMAC-SHA256 的建议量级，
    # 测试里会调低到 1000 以免拖慢用例。
    password_iterations: int = 260_000
    # 登录失败限流：窗口内同一账号在同一来源的失败次数，以及同一来源的
    # 失败总数，任一达到上限即暂停该来源的登录尝试。不单按账号锁定，
    # 否则任何人都能反复输错把指定用户锁在门外。
    login_failure_window_seconds: int = Field(default=900, ge=1)
    login_max_failures_per_account: int = Field(default=5, ge=1)
    login_max_failures_per_ip: int = Field(default=30, ge=1)
    # 前置反向代理的层数。0 表示直连，忽略 X-Forwarded-For，
    # 否则客户端可以伪造来源地址绕过限流并污染审计。
    trusted_proxy_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        if self.environment != "production":
            return self
        if not self.database_url.startswith("postgresql"):
            raise ValueError("Production requires an explicit PostgreSQL database")
        if self.crypto_key == DEV_CRYPTO_KEY or len(self.crypto_key) < 32:
            raise ValueError("Production requires a unique KG_CRYPTO_KEY")
        if self.create_tables_on_startup:
            raise ValueError("Production requires KG_CREATE_TABLES_ON_STARTUP=false")
        if self.expose_reset_token:
            raise ValueError("Production cannot expose password reset tokens")
        return self


@lru_cache
def get_settings() -> Settings:
    """单例配置，避免重复读取环境变量。"""
    return Settings()
