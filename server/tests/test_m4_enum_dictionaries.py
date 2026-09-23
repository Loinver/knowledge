"""M-05 枚举字典：API、版本快照、属性引用和迁移保护。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.api.errors import install_error_handler
from app.api.v1.enum_dictionaries import legacy_router, router
from app.core.db import Base, get_session
from app.core.errors import KGError
from app.domain.enum_dictionary_service import (
    get_snapshot,
    list_references,
    resolve_reference,
)
from app.domain.iri_service import register_namespace
from app.domain.type_service import create_entity_type
from app.models.resource import DatatypePropDetail
from app.schemas.type import DataTypePropCreate, EntityTypeCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
URL = "/api/v1/governance/enum-dictionaries"
LEGACY_URL = "/api/v1/governance/enums"


def dictionary_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "StatusKind",
        "label_i18n": {"zh-CN": "状态", "en-US": "Status"},
        "definition_i18n": {
            "zh-CN": "业务状态枚举",
            "en-US": "Business status enum",
        },
        "entries": [
            {
                "value": "OPEN",
                "label_i18n": {"zh-CN": "开放", "en-US": "Open"},
            },
            {
                "value": "CLOSED",
                "label_i18n": {"zh-CN": "关闭", "en-US": "Closed"},
            },
        ],
        **overrides,
    }


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/enum-dictionaries.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(legacy_router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: sessions()
    with TestClient(app) as test_client:
        yield test_client


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post(URL, json=dictionary_payload(**overrides))
    assert response.status_code == 201, response.text
    assert response.headers["etag"] == '"1"'
    return response.json()


def test_crud_search_history_and_legacy_alias(client: TestClient) -> None:
    created = create(client)
    assert created["revision"] == 1
    assert created["entries"][0]["value"] == "OPEN"

    listed = client.get(URL, params={"q": "OPEN"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert client.get(URL, params={"q": "开放"}).json()["total"] == 1

    legacy = client.get(LEGACY_URL, params={"q": "StatusKind"})
    assert legacy.status_code == 200
    assert legacy.json()["total"] == 1
    fetched = client.get(f"{URL}/{created['id']}")
    assert fetched.json() == created
    assert fetched.headers["etag"] == '"1"'

    updated = client.put(
        f"{URL}/{created['id']}",
        headers={"If-Match": '"1"'},
        json=dictionary_payload(
            entries=[
                {"value": "OPEN", "label_i18n": {"zh-CN": "开放"}},
                {"value": "PAUSED", "label_i18n": {"zh-CN": "暂停"}},
            ]
        ),
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.headers["etag"] == '"2"'

    revisions = client.get(f"{URL}/{created['id']}/revisions")
    assert revisions.status_code == 200
    history = revisions.json()
    assert [item["revision"] for item in history] == [2, 1]
    assert {entry["value"] for entry in history[1]["entries"]} == {"OPEN", "CLOSED"}

    stale = client.put(
        f"{URL}/{created['id']}",
        headers={"If-Match": "1"},
        json=dictionary_payload(),
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "KG.REVISION_CONFLICT"
    missing = client.put(f"{URL}/{created['id']}", json=dictionary_payload())
    assert missing.status_code == 400
    assert missing.json()["code"] == "KG.INVALID_REQUEST"


def test_validation_duplicate_name_and_values(client: TestClient) -> None:
    create(client)
    duplicate = client.post(URL, json=dictionary_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "KG.ALREADY_EXISTS"

    missing_zh = client.post(
        URL,
        json=dictionary_payload(label_i18n={"en-US": "Status"}),
    )
    assert missing_zh.status_code == 400
    assert missing_zh.json()["code"] == "KG.INVALID_REQUEST"

    duplicate_entry = client.post(
        URL,
        json=dictionary_payload(
            name="OtherKind",
            entries=[
                {"value": "X", "label_i18n": {"zh-CN": "甲"}},
                {"value": "X", "label_i18n": {"zh-CN": "乙"}},
            ],
        ),
    )
    assert duplicate_entry.status_code == 400
    assert duplicate_entry.json()["code"] == "KG.INVALID_REQUEST"


def test_explicit_reference_default_validation_and_delete_protection(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    created = create(client)
    with sessions() as session:
        with pytest.raises(KGError) as missing_revision:
            resolve_reference(session, "enum", created["id"], None, "OPEN")
        assert (
            missing_revision.value.params["reason"]
            == "enum_dictionary_revision_required"
        )
        with pytest.raises(KGError) as bad_default:
            resolve_reference(session, "enum", created["id"], 1, "MISSING")
        assert bad_default.value.code.value == "KG.VALIDATION_VIOLATION"

        namespace = register_namespace(session, "kg", "https://example.org/kg#")
        resource = create_entity_type(
            session,
            EntityTypeCreate(
                name="Employee",
                namespace_id=namespace.id,
                label_i18n={"zh-CN": "员工"},
                data_props=[
                    DataTypePropCreate(
                        name="status",
                        datatype="enum",
                        enum_dict_id=created["id"],
                        enum_dict_revision=1,
                        default_value="OPEN",
                    )
                ],
            ),
        )
        session.commit()
        refs = list_references(session, created["id"])
        assert len(refs) == 1
        assert refs[0].enum_dict_revision == 1
        assert session.scalar(select(DatatypePropDetail.enum_dict_revision)) == 1
        snapshot = get_snapshot(session, created["id"], 1)
        assert snapshot["entries"][1]["value"] == "CLOSED"
        assert resource.id > 0

    references = client.get(f"{URL}/{created['id']}/references")
    assert references.status_code == 200
    assert references.json()[0]["enum_dict_revision"] == 1
    blocked = client.delete(f"{URL}/{created['id']}", headers={"If-Match": "1"})
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "KG.REVISION_CONFLICT"
    assert blocked.json()["params"]["reason"] == "enum_dictionary_in_use"


def test_constraints_and_migration_guard(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path}/enum-migration.db"
    environment = {**os.environ, "KG_DATABASE_URL": database_url}

    def migrate(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if check:
            assert result.returncode == 0, result.stderr
        return result

    migrate("upgrade", "0008_enum_dictionaries")
    engine = create_engine(database_url)
    assert "edit_revision" not in {
        column["name"] for column in inspect(engine).get_columns("model_resource")
    }
    foreign_keys = inspect(engine).get_foreign_keys("datatype_prop_detail")
    assert {foreign_key["name"] for foreign_key in foreign_keys} >= {
        "fk_prop_enum_dictionary",
        "fk_prop_enum_revision",
    }
    migrate("upgrade", "head")
    assert "edit_revision" in {
        column["name"] for column in inspect(engine).get_columns("model_resource")
    }
    migrate("downgrade", "0008_enum_dictionaries")
    assert "edit_revision" not in {
        column["name"] for column in inspect(engine).get_columns("model_resource")
    }
    engine.dispose()

    legacy_url = f"sqlite:///{tmp_path}/enum-legacy.db"
    legacy_env = {**os.environ, "KG_DATABASE_URL": legacy_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0007_accounts"],
        cwd=ROOT,
        env=legacy_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    legacy_engine = create_engine(legacy_url)
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO namespace (prefix, iri, protected) "
                "VALUES ('kg', 'https://example.org/kg#', 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO model_resource "
                "(kind, name, iri, namespace_id, status, current_revision) "
                "VALUES ('DATATYPE_PROP', 'Legacy.status', "
                "'https://example.org/kg#Legacy/status', 1, 'DRAFT', 0)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO datatype_prop_detail "
                "(resource_id, prop_name, datatype, enum_dict_id, nullable) "
                "VALUES (1, 'status', 'enum', 99, 1)"
            )
        )
    failed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0008_enum_dictionaries"],
        cwd=ROOT,
        env=legacy_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert failed.returncode != 0
    assert "Unresolved legacy enum references" in failed.stderr
    assert "enum_dictionary" not in inspect(legacy_engine).get_table_names()
    legacy_engine.dispose()
