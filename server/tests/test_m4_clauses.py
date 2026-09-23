"""M-03 标准条款资料库：CRUD、双语校验、原子版本、重复冲突与迁移重放。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.api.errors import install_error_handler
from app.api.v1.clauses import router
from app.core.db import Base, get_session
from app.domain import clause_service
from app.models.governance import StandardClause
from app.schemas.governance import StandardClauseCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
URL = "/api/v1/governance/clauses"


def clause_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "standard": "GB/T 9386-2024",
        "clause_number": "7.2",
        "title_i18n": {"zh-CN": "对象属性装配", "en-US": "Object property assembly"},
        "self_authored_description": {
            "zh-CN": "自撰说明：对象属性的装配落点。",
            "en-US": "Self-authored note on assembly placement.",
        },
        "product_fallback": "装配模板 T-07",
        "appendix_nature": "NORMATIVE",
        "date_lexicon": "日期词法自撰说明",
        "clause_disambiguation": "与 7.3 的区分自撰说明",
        "example_domain": "制造领域示例",
        **overrides,
    }


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/clauses.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: sessions()
    with TestClient(app) as client:
        yield client


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post(URL, json=clause_payload(**overrides))
    assert response.status_code == 201, response.text
    assert response.headers["etag"] == '"1"'
    return response.json()


def test_crud_paging_and_search(client: TestClient) -> None:
    first = create(client)
    second = create(client, clause_number="7.3", product_fallback="装配模板 T-08")
    assert first["revision"] == 1
    assert first["appendix_nature"] == "NORMATIVE"
    # 索引默认序：标准号 → 条款号升序（7.2 在 7.3 之前），分页按此顺序切分。
    response = client.get(URL, params={"page_size": 1})
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": first["id"],
                "standard": first["standard"],
                "clause_number": "7.2",
                "product_fallback": "装配模板 T-07",
            }
        ],
        "total": 2,
        "page": 1,
        "page_size": 1,
    }
    assert client.get(URL, params={"page": 2, "page_size": 1}).json()["items"] == [
        {
            "id": second["id"],
            "standard": second["standard"],
            "clause_number": "7.3",
            "product_fallback": "装配模板 T-08",
        }
    ]
    # 显式排序可与索引默认序相反，用于「最近维护在前」。
    assert (
        client.get(URL, params={"sort": "-id"}).json()["items"][0]["id"] == second["id"]
    )
    assert (
        client.get(URL, params={"sort": "-clause_number"}).json()["items"][0][
            "clause_number"
        ]
        == "7.3"
    )
    # 搜索覆盖标准号、条款号、产品落点与双语标题、自撰说明。
    for query in (
        "7.2",
        "GB/T",
        "T-08",
        "对象属性装配",
        "Object property assembly",
        "装配落点",
    ):
        assert client.get(URL, params={"q": query}).json()["total"] >= 1
    assert client.get(URL, params={"q": "%"}).json()["total"] == 0
    fetched = client.get(f"{URL}/{first['id']}")
    assert fetched.json() == first
    assert fetched.headers["etag"] == '"1"'
    updated = client.put(
        f"{URL}/{first['id']}",
        headers={"If-Match": '"1"'},
        json={"product_fallback": "装配模板 T-09"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    assert updated.json()["product_fallback"] == "装配模板 T-09"
    assert updated.headers["etag"] == '"2"'
    deleted = client.delete(f"{URL}/{first['id']}", headers={"If-Match": "2"})
    assert deleted.status_code == 200
    assert client.get(f"{URL}/{first['id']}").status_code == 404


def test_bilingual_zh_cn_required(client: TestClient) -> None:
    response = client.post(
        URL, json=clause_payload(title_i18n={"en-US": "missing zh-CN"})
    )
    assert response.status_code == 400
    assert response.json()["code"] == "KG.INVALID_REQUEST"
    response = client.post(
        URL,
        json=clause_payload(self_authored_description={"zh-CN": "   "}),
    )
    assert response.status_code == 400


def test_duplicate_clause_conflicts(client: TestClient) -> None:
    create(client)
    response = client.post(URL, json=clause_payload())
    assert response.status_code == 409
    assert response.json()["code"] == "KG.ALREADY_EXISTS"


def test_appendix_nature_only_accepts_the_two_declared_values(
    client: TestClient,
) -> None:
    """附录性质是枚举码，非法值不得入库。"""
    assert (
        create(client, appendix_nature="INFORMATIVE")["appendix_nature"]
        == "INFORMATIVE"
    )
    rejected = client.post(
        URL, json=clause_payload(clause_number="8.1", appendix_nature="OTHER")
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "KG.INVALID_REQUEST"


def test_unknown_sort_is_rejected(client: TestClient) -> None:
    create(client)
    response = client.get(URL, params={"sort": "self_authored_description"})
    assert response.status_code == 400
    assert response.json()["code"] == "KG.INVALID_REQUEST"


def test_migration_upgrade_downgrade_replays_clause_index(tmp_path: Path) -> None:
    """0005 迁移须能在已有部署上升级、降级并重放，且不触碰用户既有数据。"""
    database_url = f"sqlite:///{tmp_path}/clause-migration.db"
    environment = {**os.environ, "KG_DATABASE_URL": database_url}

    def migrate(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "head")
    engine = create_engine(database_url)
    assert "standard_clause" in inspect(engine).get_table_names()
    with Session(engine) as session:
        clause_service.create_clause(session, StandardClauseCreate(**clause_payload()))
        session.commit()
        assert session.scalar(select(StandardClause.clause_number)) == "7.2"
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO namespace (prefix, iri, protected) VALUES (:p, :i, 0)"),
            {"p": "example", "i": "https://example.org/"},
        )

    migrate("downgrade", "0004_assembly_templates")
    assert "standard_clause" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT prefix FROM namespace")) == "example"

    migrate("upgrade", "head")
    assert "standard_clause" in inspect(engine).get_table_names()
    with Session(engine) as session:
        replayed = clause_service.create_clause(
            session, StandardClauseCreate(**clause_payload())
        )
        session.commit()
        assert replayed.clause_number == "7.2"
        assert session.scalar(select(StandardClause.standard)) == "GB/T 9386-2024"
    engine.dispose()


def test_revision_conflict_and_missing_if_match(client: TestClient) -> None:
    created = create(client)
    stale = client.put(
        f"{URL}/{created['id']}",
        headers={"If-Match": '"999"'},
        json={"product_fallback": "过期写入"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "KG.REVISION_CONFLICT"
    missing = client.put(
        f"{URL}/{created['id']}", json={"product_fallback": "缺少版本头"}
    )
    assert missing.status_code == 400
    stale_delete = client.delete(f"{URL}/{created['id']}", headers={"If-Match": "999"})
    assert stale_delete.status_code == 409
