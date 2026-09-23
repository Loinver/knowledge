"""应用生命周期使用替身引擎，绝不连接用户元数据库。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app import main
from fastapi import FastAPI


@pytest.mark.parametrize("create_tables", [False, True])
def test_lifespan_creates_tables_only_when_enabled_and_disposes(
    monkeypatch: pytest.MonkeyPatch, create_tables: bool
) -> None:
    engine = Mock()
    create_all = Mock()
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    monkeypatch.setattr(main.Base.metadata, "create_all", create_all)
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: SimpleNamespace(create_tables_on_startup=create_tables),
    )

    async def run() -> None:
        async with main.lifespan(FastAPI()):
            assert create_all.call_count == int(create_tables)
            engine.dispose.assert_not_called()

    asyncio.run(run())
    engine.dispose.assert_called_once_with()
    if create_tables:
        create_all.assert_called_once_with(engine)


@pytest.mark.parametrize("fail_during_startup", [False, True])
def test_lifespan_disposes_on_startup_or_application_failure(
    monkeypatch: pytest.MonkeyPatch, fail_during_startup: bool
) -> None:
    engine = Mock()
    create_all = Mock(
        side_effect=RuntimeError("startup") if fail_during_startup else None
    )
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    monkeypatch.setattr(main.Base.metadata, "create_all", create_all)
    monkeypatch.setattr(
        main, "get_settings", lambda: SimpleNamespace(create_tables_on_startup=True)
    )

    async def run() -> None:
        async with main.lifespan(FastAPI()):
            raise RuntimeError("application")

    with pytest.raises(
        RuntimeError, match="startup" if fail_during_startup else "application"
    ):
        asyncio.run(run())
    engine.dispose.assert_called_once_with()
