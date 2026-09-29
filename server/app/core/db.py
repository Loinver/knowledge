"""数据库 session 与声明式基类。

SQLAlchemy 2.0 风格。写接口的事务边界由调用方（API 路由或领域编排）
用 `with session.begin()` 控制；这里只提供工厂与基类。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


_engine = create_engine(
    get_settings().database_url,
    # SQLite 需要这个才能在多线程/async 下正常工作
    connect_args={"check_same_thread": False}
    if _is_sqlite(get_settings().database_url)
    else {},
    echo=False,
)
# SQLite 默认不强制外键；模型声明的 FK 只有开启 pragma 才生效。
# 不开的话，删除父行会静默留下孤儿子行（数据损坏）。
if _is_sqlite(get_settings().database_url):

    @event.listens_for(_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


_SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)


def get_engine() -> Engine:
    """暴露 engine 供 Alembic 与初始化脚本使用。"""
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个 session，请求结束归还连接。

    必须是生成器依赖——FastAPI 只在生成器依赖上执行 `finally`。
    若直接 `return _SessionFactory()`，连接就只借不还：连接池（默认 5+10）
    耗尽后，所有需要数据库的请求都会卡到 30 秒超时。
    """
    session = _SessionFactory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """事务上下文：成功提交，异常回滚。领域服务与测试使用。"""
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def bound_scope(factory: sessionmaker) -> Iterator[Session]:
    """绑定任意引擎工厂的事务上下文（异步任务线程使用）。"""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
