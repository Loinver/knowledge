"""`get_session` 依赖必须归还数据库连接。

曾经的写法是 `return _SessionFactory()`——普通函数依赖，FastAPI 不会对它执行
任何清理，连接只借不还。连接池（默认 size=5 + overflow=10）耗尽后，所有需要
数据库的请求都会卡到 30 秒超时再报 500，而健康检查这类不碰库的接口照常 200，
现场看起来像是「某些接口莫名挂住」。
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Iterator

from app.core.db import get_engine, get_session
from sqlalchemy import text


def test_get_session_is_a_generator_dependency() -> None:
    """普通函数依赖拿不到 FastAPI 的清理钩子，必须写成生成器。"""
    assert inspect.isgeneratorfunction(get_session)


def test_get_session_returns_its_connection_to_the_pool() -> None:
    pool = get_engine().pool
    baseline = pool.checkedout()

    dependency: Iterator[object] = get_session()
    session = next(dependency)
    session.execute(text("SELECT 1"))  # 真正借出连接
    assert pool.checkedout() == baseline + 1

    with contextlib.suppress(StopIteration):
        next(dependency)  # 生成器结束 → finally 归还连接

    assert pool.checkedout() == baseline
