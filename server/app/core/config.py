"""应用配置（pydantic-settings）。

开发态默认 SQLite（单文件、零依赖），生产用 PostgreSQL。
元数据库与被抽取的源库物理分离——这是硬约束。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    database_url: str = "sqlite:///./knowledge.db"
    crypto_key: str = "dev-only-do-not-use-in-production-key-32bytes!"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    """单例配置，避免重复读取环境变量。"""
    return Settings()
