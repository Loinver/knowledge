"""来源证据追溯（H-42）。

验收：8 步贯通第 7 步——从图谱任一三元组反查到 fact_evidence，
每条事实摊平为 主体·谓词·客体·来源连接/表/行键/字段·运行批次·证据类型。
来源被隔离时 quarantined=True，不伪装证据完整。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.v1.extraction import router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError, install_error_handler
from app.domain.evidence_service import trace_entity_evidence, trace_fact
from app.domain.extraction_service import (
    get_current_graph,
    get_evidence,
    get_run,
    list_triples,
    start_run,
    switch_current,
)
from app.domain.mapping_service import (
    create_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.source_service import create_datasource
from app.models.data_access import Datasource
from app.models.domain import Ontology, OntologyRevision
from app.models.extraction import EntityIdentity, Quarantine
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
    RelMapCreate,
    RelMode,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def _make_source(path: str) -> None:
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE enterprise ("
                "id INTEGER PRIMARY KEY, name TEXT, credit_code TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE hr_employee ("
                "id INTEGER PRIMARY KEY, name TEXT, enterprise_id INTEGER, "
                "FOREIGN KEY (enterprise_id) REFERENCES enterprise(id))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO enterprise (id, name, credit_code) VALUES "
                "(1001, '企业A', 'C001')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO hr_employee (id, name, enterprise_id) VALUES "
                "(8001, '张三', 1001)"
            )
        )
        conn.commit()


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    url = f"sqlite:///{tmp_path}/kg.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = sf()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def source_db(tmp_path: Path) -> Iterator[str]:
    path = str(tmp_path / "src.db")
    _make_source(path)
    yield path


def _setup(session: Session, source_db: str) -> Datasource:
    onto = Ontology(
        name="o1",
        iri="https://example.org/o1#",
        status="PUBLISHED",
        current_revision=1,
    )
    session.add(onto)
    session.flush()
    rev = OntologyRevision(
        ontology_id=onto.id,
        revision=1,
        ref_domains=[],
        ref_types=[],
        rules=[],
        resource_versions={},
    )
    session.add(rev)
    session.flush()
    ds = create_datasource(
        session,
        DatasourceCreate(name="ds1", kind="sqlite", params={"database": source_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    m = create_mapping(session, MappingCreate(name="m1", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="Enterprise",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
                EntityMapCreate(
                    entity_type="Employee",
                    table="hr_employee",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
            ],
            rel_maps=[
                RelMapCreate(
                    relation_type="works_for",
                    mode=RelMode.FK,
                    table="hr_employee",
                    fk_field="enterprise_id",
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    map_rev = publish_mapping(session, m.id, if_match=0)
    session.commit()
    start_run(session, map_rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    return ds


def test_trace_fact_returns_full_chain(session: Session, source_db: str) -> None:
    """从一条三元组反查到完整追溯链。"""
    _setup(session, source_db)
    gr = get_current_graph(session)
    assert gr is not None

    triples, _ = list_triples(session, gr.id)
    fk_triples = [t for t in triples if t.predicate == "works_for"]
    assert len(fk_triples) >= 1
    t = fk_triples[0]

    result = trace_fact(session, t.subject, t.predicate, t.object_)
    assert result["fact"]["subject"] == t.subject
    assert result["fact"]["predicate"] == t.predicate
    assert result["fact"]["object"] == t.object_

    assert result["total_count"] >= 1
    ev = result["evidences"][0]
    assert ev["table_name"] == "hr_employee"
    assert ev["evidence_type"] == "RELATION"
    assert "enterprise_id" in ev["columns"]
    assert ev["source_name"] == "ds1"
    assert ev["source_kind"] == "sqlite"
    assert ev["run_id"] is not None


def test_trace_fact_not_found(session: Session, source_db: str) -> None:
    """事实不存在时报 RESOURCE_NOT_FOUND。"""
    _setup(session, source_db)
    with pytest.raises(KGError) as exc:
        trace_fact(session, "x", "y", "z")
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_trace_entity_evidence(session: Session, source_db: str) -> None:
    """实体维度的证据汇总。"""
    _setup(session, source_db)
    gr = get_current_graph(session)
    assert gr is not None

    triples, _ = list_triples(session, gr.id)
    # 取一个 Employee 实体 IRI
    emp_iris = [t.subject for t in triples if t.predicate == "works_for"]
    assert len(emp_iris) >= 1

    result = trace_entity_evidence(session, emp_iris[0])
    assert result["entity"]["iri"] == emp_iris[0]
    assert result["total_count"] >= 1
    assert result["quarantined_count"] == 0


def test_trace_quarantine_flag(session: Session, source_db: str) -> None:
    """来源被隔离时 quarantined=True。"""
    _setup(session, source_db)
    gr = get_current_graph(session)
    assert gr is not None

    # 检查正常运行的证据 quarantined 都是 False
    triples, _ = list_triples(session, gr.id)
    t = triples[0]
    result = trace_fact(session, t.subject, t.predicate, t.object_)
    assert result["quarantined_count"] == 0
    for ev in result["evidences"]:
        assert ev["quarantined"] is False


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app = FastAPI()
    install_error_handler(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


def test_trace_is_pinned_to_graph_and_quarantine_run(
    session: Session, source_db: str, client: TestClient
) -> None:
    """切换前后只返回所选结果集；历史行的隔离记录不能污染新运行。"""
    ds = _setup(session, source_db)
    old_graph = get_current_graph(session)
    assert old_graph is not None
    triples, _ = list_triples(session, old_graph.id)
    fact = triples[0]
    session.add(
        Quarantine(
            run_id=old_graph.run_id,
            table_name="hr_employee",
            row_key="8001",
            field="name",
            raw_value=None,
            transform_chain=["required"],
            rule_id="required_violation",
        )
    )
    session.flush()
    old_run = get_run(session, old_graph.run_id)
    start_run(session, old_run.mapping_revision_id, ds.id)
    session.commit()
    new_graph = get_current_graph(session)
    assert new_graph is not None and new_graph.id != old_graph.id

    current = trace_fact(session, fact.subject, fact.predicate, fact.object_)
    assert current["graph_revision_id"] == new_graph.id
    assert current["quarantined_count"] == 0
    assert {e["run_id"] for e in current["evidences"]} == {new_graph.run_id}
    old = trace_fact(session, fact.subject, fact.predicate, fact.object_, old_graph.id)
    assert old["quarantined_count"] == 1
    assert old["evidences"][0]["quarantined"] is True
    assert {
        e.run_id
        for e in get_evidence(session, fact.subject, fact.predicate, fact.object_)
    } == {new_graph.run_id}

    switch_current(session, old_graph.id)
    session.commit()
    query = {
        "subject": fact.subject,
        "predicate": fact.predicate,
        "object": fact.object_,
    }
    default = client.get("/api/v1/extraction/evidence/trace", params=query)
    assert default.status_code == 200
    assert default.json()["graph_revision_id"] == old_graph.id
    pinned = client.get(
        "/api/v1/extraction/evidence/trace",
        params={**query, "graph_revision_id": new_graph.id},
    )
    assert pinned.status_code == 200
    assert pinned.json()["graph_revision_id"] == new_graph.id
    assert pinned.json()["quarantined_count"] == 0
    # 旧证据接口同样不能混入历史运行。
    legacy = client.get("/api/v1/extraction/evidence", params=query)
    assert {e["run_id"] for e in legacy.json()} == {old_graph.run_id}


def test_entity_api_pagination_search_and_special_iri(
    session: Session, source_db: str, client: TestClient
) -> None:
    _setup(session, source_db)
    gr = get_current_graph(session)
    assert gr is not None
    special_iri = "https://example.org/kg/#员工/1?scope=a%2Fb"
    for index in range(205):
        session.add(
            EntityIdentity(
                graph_revision_id=gr.id,
                iri=special_iri
                if index == 0
                else f"https://example.org/Extra/{index:04}",
                type_iri="https://example.org/Extra",
                row_key=f"extra-{index:04}",
                attrs={"name": f"Entity {index}"},
            )
        )
    session.commit()
    response = client.get(
        "/api/v1/extraction/entities", params={"page": 3, "page_size": 100}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 207
    assert len(data["items"]) == 7
    assert data["page"] == 3 and data["page_size"] == 100
    assert data["graph_revision_id"] == gr.id
    by_row = client.get(
        "/api/v1/extraction/entities", params={"q": "extra-0204"}
    ).json()
    assert by_row["total"] == 1
    by_name = client.get(
        "/api/v1/extraction/entities", params={"q": "Entity 204"}
    ).json()
    assert by_name["total"] == 1
    assert by_name["items"][0]["row_key"] == "extra-0204"
    # 搜索内容不是 SQL LIKE 通配符。
    by_percent = client.get("/api/v1/extraction/entities", params={"q": "%"}).json()
    assert by_percent["total"] == 1
    assert by_percent["items"][0]["iri"] == special_iri
    descending = client.get(
        "/api/v1/extraction/entities", params={"sort": "-iri"}
    ).json()
    iris = [item["iri"] for item in descending["items"]]
    assert iris == sorted(iris, reverse=True)

    detail = client.get(
        "/api/v1/extraction/entity-detail",
        params={"iri": special_iri, "graph_revision_id": gr.id},
    )
    assert detail.status_code == 200
    assert detail.json()["entity"]["iri"] == special_iri
    assert set(detail.json()) == {
        "entity",
        "out_edges",
        "in_edges",
        "derived_edges",
        "evidence",
    }
    assert detail.json()["entity"]["attrs"] == {"name": "Entity 0"}


def test_entity_evidence_api_shape_and_no_connection_secrets(
    session: Session, source_db: str, client: TestClient
) -> None:
    _setup(session, source_db)
    listed = client.get("/api/v1/extraction/entities").json()
    entity = next(item for item in listed["items"] if "Employee" in item["iri"])
    response = client.get(
        "/api/v1/extraction/evidence/trace/entity", params={"iri": entity["iri"]}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == len(data["evidences"]) == 2
    for ev in data["evidences"]:
        assert set(ev) == {
            "id",
            "subject",
            "predicate",
            "object",
            "source_id",
            "source_name",
            "source_kind",
            "table_name",
            "row_key",
            "columns",
            "run_id",
            "evidence_type",
            "quarantined",
        }
        assert ev["source_name"] == "ds1"
        assert ev["columns"]
    schema = client.get("/openapi.json").json()
    response_schema = schema["paths"]["/api/v1/extraction/entity-detail"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/EntityDetailOut")


def test_graph_reads_reject_missing_graph_and_invalid_pagination(
    client: TestClient,
) -> None:
    for path, params in [
        ("entities", {}),
        ("entity-detail", {"iri": "missing"}),
        ("evidence/trace/entity", {"iri": "missing"}),
        ("evidence/trace", {"subject": "s", "predicate": "p", "object": "o"}),
    ]:
        response = client.get(f"/api/v1/extraction/{path}", params=params)
        assert response.status_code == 404
        assert response.json()["code"] == "KG.RESOURCE_NOT_FOUND"
    for params in (
        {"page": 0},
        {"page_size": 201},
        {"sort": "invalid"},
        {"graph_revision_id": 0},
    ):
        assert (
            client.get("/api/v1/extraction/entities", params=params).status_code == 422
        )
