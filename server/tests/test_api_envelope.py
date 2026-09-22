"""统一响应外壳契约测试。

所有 JSON 接口必须返回 `{ code, message, data }`：

- 成功：`code == "KG.OK"`，业务数据在 `data` 里；无数据时 `data` 为 `null`。
- 失败：结构同构，`code` 为错误码，`params` 带结构化参数，`data` 恒为 `null`。
- 删除类接口返回 200 + 空 `data`，不再是 204 空响应。

二进制导出（turtle / json-ld）不包裹，保持原样下载。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.api.v1.namespaces import router
from app.core.db import Base, get_session
from app.core.errors import install_error_handler
from app.schemas.response import OK_CODE
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

URL = "/api/v1/namespaces"


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/envelope.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    # 不走应用启动事件，避免在用户配置的数据库里建表。
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: sessions()
    with TestClient(app) as test_client:
        yield test_client


def raw(response: Any) -> dict[str, Any]:
    """取未经解包的原始外壳（绕过 conftest 的测试解包垫片）。"""
    return dict(json.loads(response.text))


def test_list_response_is_wrapped(client: TestClient) -> None:
    body = raw(client.get(URL))
    assert body["code"] == OK_CODE
    assert body["message"] == "OK"
    assert body["data"] == []


def test_create_response_is_wrapped(client: TestClient) -> None:
    response = client.post(URL, json={"prefix": "ex", "iri": "https://example.org/"})
    assert response.status_code == 201
    body = raw(response)
    assert body["code"] == OK_CODE
    assert body["data"]["prefix"] == "ex"


def test_delete_returns_ok_with_null_data(client: TestClient) -> None:
    created = raw(
        client.post(URL, json={"prefix": "ex", "iri": "https://example.org/"})
    )
    namespace_id = created["data"]["id"]
    response = client.delete(f"{URL}/{namespace_id}")
    assert response.status_code == 200
    assert raw(response) == {"code": OK_CODE, "message": "OK", "data": None}


def test_error_response_shares_the_same_shape(client: TestClient) -> None:
    response = client.delete(f"{URL}/404")
    assert response.status_code == 404
    body = raw(response)
    assert body["code"] == "KG.RESOURCE_NOT_FOUND"
    assert body["data"] is None
    assert body["params"]["id"] == 404


def test_request_validation_error_is_wrapped(client: TestClient) -> None:
    response = client.post(URL, json={"prefix": 123})
    # 保持 FastAPI 原生 422（请求不可处理），只把响应体换成统一外壳。
    assert response.status_code == 422
    body = raw(response)
    assert body["code"] == "KG.INVALID_REQUEST"
    assert body["data"] is None
    assert body["params"]["issues"]
