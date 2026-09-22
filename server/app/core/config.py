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

    # --- 账号模块 ---
    # 公开注册默认关闭：账号由管理员在用户管理里创建，首个管理员用
    # `make seed-admin` 生成（见 docs/adr/0002-account-auth.md）。
    allow_public_registration: bool = False
    # 开发态没有邮件服务，忘记密码接口直接把重置令牌放在响应里，
    # **生产必须置 0**（KG_EXPOSE_RESET_TOKEN=0），否则等于开放改密入口。
    expose_reset_token: bool = True
    # 令牌有效期：访问令牌短、刷新令牌长；重置令牌只够走完一次改密。
    access_token_ttl_seconds: int = 3600
    refresh_token_ttl_seconds: int = 1_209_600
    reset_token_ttl_seconds: int = 3600
    # 口令派生迭代次数。默认值按 OWASP 对 PBKDF2-HMAC-SHA256 的建议量级，
    # 测试里会调低到 1000 以免拖慢用例。
    password_iterations: int = 260_000


@lru_cache
def get_settings() -> Settings:
    """单例配置，避免重复读取环境变量。"""
    return Settings()
