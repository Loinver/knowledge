"""M-07 补齐的属性与关系约束：类型/枚举/可空/默认值、基数与 OWL 特征。

M1 阶段这些字段只在 API 层被接受、写库时丢弃；本文件锁定「不再静默丢字段」：
创建 → 读取 → 更新 → 读取全程无损，且发布快照一并冻结约束。
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.api.v1.namespaces import router as namespaces_router
from app.api.v1.relations import router as relations_router
from app.api.v1.types import router as types_router
from app.core.db import Base, get_session
from app.core.errors import install_error_handler
from app.domain.enum_dictionary_service import create_dictionary
from app.domain.relation_service import create_relation_type, get_relation_meta
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type, get_data_props, get_prop_detail
from app.models.resource import DatatypePropDetail, ObjectPropDetail, ResourceRevision
from app.schemas.enum_dictionary import EnumDictionaryInput
from app.schemas.relation import (
    CardinalitySpec,
    EndpointSpec,
    OwlFeatures,
    RelationTypeCreate,
)
from app.schemas.type import DataTypePropCreate, EntityTypeCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/props.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        create_dictionary(
            session,
            EnumDictionaryInput(
                name="EmployeeLevel",
                label_i18n={"zh-CN": "职级"},
                definition_i18n={"zh-CN": "员工职级"},
                entries=[{"value": "P3", "label_i18n": {"zh-CN": "三级"}}],
            ),
        )
        session.commit()
    yield factory
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    for router in (namespaces_router, types_router, relations_router):
        app.include_router(router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: sessions()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def namespace_id(client: TestClient) -> int:
    response = client.post(
        "/api/v1/namespaces", json={"prefix": "kg", "iri": "https://example.org/kg#"}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def make_type(
    client: TestClient, namespace_id: int, props: list[dict[str, Any]]
) -> dict:
    response = client.post(
        "/api/v1/entity-types",
        json={
            "name": "Employee",
            "namespace_id": namespace_id,
            "label_i18n": {"zh-CN": "员工", "en-US": "Employee"},
            "data_props": props,
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


# ---------------------------------------------------------------------------
# 数据属性：数据类型 / 枚举引用 / 可空 / 默认值
# ---------------------------------------------------------------------------


def test_data_prop_constraints_survive_create_and_read(
    client: TestClient, namespace_id: int
) -> None:
    created = make_type(
        client,
        namespace_id,
        [
            {"name": "code", "datatype": "string", "nullable": False},
            {
                "name": "level",
                "datatype": "enum",
                "enum_dict_id": 1,
                "enum_dict_revision": 1,
                "nullable": True,
                "default_value": "P3",
                "label_i18n": {"zh-CN": "职级"},
            },
        ],
    )
    assert created["data_props"] == [
        {
            "name": "code",
            "label_i18n": None,
            "definition_i18n": None,
            "datatype": "string",
            "enum_dict_id": None,
            "enum_dict_revision": None,
            "nullable": False,
            "default_value": None,
        },
        {
            "name": "level",
            "label_i18n": {"zh-CN": "职级"},
            "definition_i18n": None,
            "datatype": "enum",
            "enum_dict_id": 1,
            "enum_dict_revision": 1,
            "nullable": True,
            "default_value": "P3",
        },
    ]


def test_new_enum_property_requires_explicit_dictionary_revision(
    client: TestClient, namespace_id: int
) -> None:
    response = client.post(
        "/api/v1/entity-types",
        json={
            "name": "ImplicitPin",
            "namespace_id": namespace_id,
            "label_i18n": {"zh-CN": "隐式版本"},
            "data_props": [{"name": "status", "datatype": "enum", "enum_dict_id": 1}],
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "KG.INVALID_REQUEST"
    assert response.json()["params"]["reason"] == "enum_dictionary_revision_required"


def test_data_prop_constraints_survive_update(
    client: TestClient, namespace_id: int
) -> None:
    created = make_type(client, namespace_id, [{"name": "code", "datatype": "string"}])
    updated = client.put(
        f"/api/v1/entity-types/{created['id']}",
        json={
            "data_props": [
                {
                    "name": "level",
                    "datatype": "integer",
                    "nullable": False,
                    "default_value": "1",
                }
            ],
            "if_match": 0,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data_props"][0] == {
        "name": "level",
        "label_i18n": None,
        "definition_i18n": None,
        "datatype": "integer",
        "enum_dict_id": None,
        "enum_dict_revision": None,
        "nullable": False,
        "default_value": "1",
    }


def test_data_prop_detail_is_persisted_as_real_columns(
    sessions: sessionmaker[Session],
) -> None:
    from app.domain.iri_service import register_namespace

    with sessions() as session:
        ns = register_namespace(session, "kg", "https://example.org/kg#")
        resource = create_entity_type(
            session,
            EntityTypeCreate(
                name="Employee",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "员工"},
                data_props=[
                    DataTypePropCreate(
                        name="level",
                        datatype="enum",
                        enum_dict_id=1,
                        enum_dict_revision=1,
                        nullable=False,
                    )
                ],
            ),
        )
        session.commit()
        prop = get_data_props(session, resource)[0]
        detail = get_prop_detail(session, prop.id)
        assert detail is not None
        assert (detail.prop_name, detail.datatype, detail.enum_dict_id) == (
            "level",
            "enum",
            1,
        )
        assert detail.nullable is False


# ---------------------------------------------------------------------------
# 关系：端点基数、角色标签、OWL 特征
# ---------------------------------------------------------------------------


def _relation_payload(namespace_id: int, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "WorksIn",
        "namespace_id": namespace_id,
        "label_i18n": {"zh-CN": "就职于", "en-US": "works in"},
        "domain_spec": {
            "type_id": 0,
            "cardinality": {
                "min": 0,
                "max": 1,
                "role_label_i18n": {"zh-CN": "每个员工最多 1 个部门"},
            },
            "role_i18n": {"zh-CN": "任职方"},
        },
        "range_spec": {
            "type_id": 0,
            "cardinality": {"min": 0, "max": -1},
        },
    }
    payload.update(overrides)
    return payload


def test_relation_cardinality_and_owl_survive_create_and_read(
    client: TestClient, namespace_id: int
) -> None:
    employee = make_type(client, namespace_id, [])
    department = client.post(
        "/api/v1/entity-types",
        json={
            "name": "Department",
            "namespace_id": namespace_id,
            "label_i18n": {"zh-CN": "部门"},
        },
    ).json()

    payload = _relation_payload(namespace_id)
    payload["domain_spec"]["type_id"] = employee["id"]
    payload["range_spec"]["type_id"] = department["id"]
    payload["owl"] = {"functional": True, "inverse_functional": True}

    created = client.post("/api/v1/relations", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["domain_spec"] == {
        "type_id": employee["id"],
        "cardinality": {
            "min": 0,
            "max": 1,
            "role_label_i18n": {"zh-CN": "每个员工最多 1 个部门"},
        },
        "role_i18n": {"zh-CN": "任职方"},
    }
    assert body["range_spec"]["cardinality"] == {
        "min": 0,
        "max": -1,
        "role_label_i18n": None,
    }
    assert body["owl"] == {
        "functional": True,
        "inverse_functional": True,
        "symmetric": False,
        "transitive": False,
    }

    fetched = client.get(f"/api/v1/relations/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_relation_update_persists_constraints_instead_of_dropping_them(
    client: TestClient, namespace_id: int
) -> None:
    employee = make_type(client, namespace_id, [])
    department = client.post(
        "/api/v1/entity-types",
        json={
            "name": "Department",
            "namespace_id": namespace_id,
            "label_i18n": {"zh-CN": "部门"},
        },
    ).json()

    payload = _relation_payload(namespace_id)
    payload["domain_spec"]["type_id"] = employee["id"]
    payload["range_spec"]["type_id"] = department["id"]
    created = client.post("/api/v1/relations", json=payload).json()

    updated = client.put(
        f"/api/v1/relations/{created['id']}",
        json={
            "domain_spec": {
                "type_id": department["id"],
                "cardinality": {"min": 1, "max": 5},
            },
            "owl": {"transitive": True},
            "if_match": 0,
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    # 端点基数被真正改写（此前实现只校验存在性，写库时丢弃）
    assert body["domain_spec"]["type_id"] == department["id"]
    assert body["domain_spec"]["cardinality"] == {
        "min": 1,
        "max": 5,
        "role_label_i18n": None,
    }
    # 未提供的一侧从存储读回，不被默认值覆盖
    assert body["range_spec"]["type_id"] == department["id"]
    assert body["range_spec"]["cardinality"] == {
        "min": 0,
        "max": -1,
        "role_label_i18n": None,
    }
    assert body["owl"] == {
        "functional": False,
        "inverse_functional": False,
        "symmetric": False,
        "transitive": True,
    }


def test_assoc_attribute_datatype_and_nullable_survive(
    client: TestClient, namespace_id: int
) -> None:
    employee = make_type(client, namespace_id, [])
    department = client.post(
        "/api/v1/entity-types",
        json={
            "name": "Department",
            "namespace_id": namespace_id,
            "label_i18n": {"zh-CN": "部门"},
        },
    ).json()

    payload = _relation_payload(namespace_id, name="Participates")
    payload["domain_spec"]["type_id"] = employee["id"]
    payload["range_spec"]["type_id"] = department["id"]
    payload["enable_attributes"] = True
    payload["attribute_defs"] = [
        {"name": "role", "datatype": "string", "nullable": False},
        {"name": "since", "datatype": "date", "nullable": True},
    ]

    created = client.post("/api/v1/relations", json=payload)
    assert created.status_code == 201, created.text
    attrs = created.json()["attribute_defs"]
    assert attrs == [
        {
            "name": "role",
            "datatype": "string",
            "nullable": False,
            "enum_dict_id": None,
            "enum_dict_revision": None,
            "default_value": None,
        },
        {
            "name": "since",
            "datatype": "date",
            "nullable": True,
            "enum_dict_id": None,
            "enum_dict_revision": None,
            "default_value": None,
        },
    ]


# ---------------------------------------------------------------------------
# 版本冻结：约束随发布快照一起冻结
# ---------------------------------------------------------------------------


def test_publish_freezes_prop_constraints_into_revision(
    sessions: sessionmaker[Session],
) -> None:
    from app.domain.iri_service import register_namespace

    with sessions() as session:
        ns = register_namespace(session, "kg", "https://example.org/kg#")
        employee = create_entity_type(
            session,
            EntityTypeCreate(
                name="Employee",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "员工"},
                data_props=[
                    DataTypePropCreate(
                        name="level",
                        datatype="enum",
                        enum_dict_id=1,
                        enum_dict_revision=1,
                        nullable=False,
                        default_value="P3",
                    )
                ],
            ),
        )
        department = create_entity_type(
            session,
            EntityTypeCreate(
                name="Department",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "部门"},
            ),
        )
        relation = create_relation_type(
            session,
            RelationTypeCreate(
                name="WorksIn",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "就职于"},
                domain_spec=EndpointSpec(
                    type_id=employee.id,
                    cardinality=CardinalitySpec(
                        min=0,
                        max=1,
                        role_label_i18n={"zh-CN": "每个员工最多 1 个部门"},
                    ),
                ),
                range_spec=EndpointSpec(type_id=department.id),
                owl=OwlFeatures(transitive=True),
            ),
        )
        session.commit()

        publish_resource(session, employee)
        publish_resource(session, relation)
        session.commit()

        type_revision = session.scalar(
            select(ResourceRevision).where(ResourceRevision.resource_id == employee.id)
        )
        assert type_revision is not None
        assert type_revision.payload["datatype_props"] == [
            {
                "role": "data_prop",
                "name": "level",
                "iri": "https://example.org/kg#Employee/level",
                "label_i18n": None,
                "datatype": "enum",
                "enum_dict_id": 1,
                "enum_dict_revision": 1,
                "enum_dictionary": {
                    "id": 1,
                    "revision": 1,
                    "name": "EmployeeLevel",
                    "label_i18n": {"zh-CN": "职级"},
                    "definition_i18n": {"zh-CN": "员工职级"},
                    "entries": [{"value": "P3", "label_i18n": {"zh-CN": "三级"}}],
                },
                "nullable": False,
                "default_value": "P3",
            }
        ]
        assert type_revision.checksum

        relation_revision = session.scalar(
            select(ResourceRevision).where(ResourceRevision.resource_id == relation.id)
        )
        assert relation_revision is not None
        detail = relation_revision.payload["object_prop"]
        assert detail["domain_cardinality"] == {
            "min": 0,
            "max": 1,
            "role_label_i18n": {"zh-CN": "每个员工最多 1 个部门"},
        }
        assert detail["owl"]["transitive"] is True
        # 关系元数据也仍在快照里
        assert {ref["role"] for ref in relation_revision.payload["resource_refs"]} >= {
            "relation_domain",
            "relation_range",
        }
        assert get_relation_meta(session, relation)["owl"] == {
            "functional": False,
            "inverse_functional": False,
            "symmetric": False,
            "transitive": True,
        }
        assert session.get(ObjectPropDetail, relation.id) is not None
        assert session.get(DatatypePropDetail, get_data_props(session, employee)[0].id)


# ---------------------------------------------------------------------------
# 迁移：0006 升级 / 降级 / 重放
# ---------------------------------------------------------------------------


def test_migration_upgrade_downgrade_replays_prop_details(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path}/prop-migration.db"
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
    tables = inspect(engine).get_table_names()
    assert "datatype_prop_detail" in tables
    assert "object_prop_detail" in tables

    migrate("downgrade", "0005_standard_clause")
    tables = inspect(engine).get_table_names()
    assert "datatype_prop_detail" not in tables
    assert "object_prop_detail" not in tables
    assert "standard_clause" in tables

    migrate("upgrade", "head")
    tables = inspect(engine).get_table_names()
    assert "datatype_prop_detail" in tables
    assert "object_prop_detail" in tables
    engine.dispose()
