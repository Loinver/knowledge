"""数据库 session 与声明式基类。

SQLAlchemy 2.0 风格。写接口的事务边界由调用方（API 路由或领域编排）
用 `with session.begin()` 控制；这里只提供工厂与基类。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


_engine = create_engine(
    get_settings().database_url,
    # SQLite 需要这个才能在多线程/async 下正常工作
    connect_args={"check_same_thread": False}
    if get_settings().database_url.startswith("sqlite")
    else {},
    echo=False,
)
_SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)


def get_engine() -> Engine:
    """暴露 engine 供 Alembic 与初始化脚本使用。"""
    return _engine


def get_session() -> Session:
    """FastAPI 依赖：每个请求一个 session。"""
    return _SessionFactory()


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
