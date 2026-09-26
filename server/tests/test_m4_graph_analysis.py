"""图谱分析 API：diff（G-24）/ path（G-12）/ 形态推荐 / 视图模板 / 反向追溯。

必测断言：
- diff 集合差正确且与 IRI/名称无关
- path 最短路径找到与未找到两种结局
- 形态推荐：改名不变性（IRI/表名不同、结构相同 → 相同 layout_id）
- 视图模板 CRUD + 本体升级后 stale=True
- 反向追溯：源行 → 参与事实与实体
- A05/A06 真实执行：规则漂移 VIOLATION / 模板缺成员 VIOLATION / 无则 NA
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from app.api.errors import install_error_handler
from app.api.v1.extraction import router as extraction_router
from app.api.v1.graph_templates import router as templates_router
from app.core.db import Base, get_session
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import (
    AssemblyTemplate,
    Ontology,
    OntologyRevision,
    OntologyRuleRef,
)
from app.models.extraction import (
    EntityIdentity,
    ExtractionRun,
    FactEvidence,
    GraphRevision,
    GraphTriple,
)
from app.models.governance import Rule
from app.models.resource import ModelResource, Namespace, ResourceRevision
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(extraction_router, prefix="/api/v1")
    app.include_router(templates_router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


def _snapshot_payload(name: str, iri: str, kind: str, **extra: object) -> dict:
    payload = {
        "name": name,
        "iri": iri,
        "kind": kind,
        "label_i18n": {"zh-CN": name, "en-US": name},
        "definition_i18n": extra.get("definition_i18n", {}),
        "namespace": {"prefix": "ex", "iri": "https://example.org/"},
        "parent_ids": [],
        "resource_refs": extra.get("resource_refs", []),
        "datatype_props": extra.get("datatype_props", []),
    }
    if "object_prop" in extra:
        payload["object_prop"] = extra["object_prop"]
    return payload


def _setup_graph(session: Session) -> tuple[GraphRevision, GraphRevision]:
    """两个图谱版本：v2 比 v1 多一个实体和一条边。"""
    onto = Ontology(name="o", iri="https://example.org/o#", status="PUBLISHED")
    session.add(onto)
    session.flush()
    session.add(
        OntologyRevision(
            ontology_id=onto.id,
            revision=1,
            ref_domains=[],
            ref_types=[],
            rules=[],
            resource_versions={},
        )
    )
    session.flush()
    mapping = Mapping(name="m", ontology_id=onto.id)
    session.add(mapping)
    session.flush()
    rev = MappingRevision(mapping_id=mapping.id, revision=1, onto_version=1)
    session.add(rev)
    session.flush()

    def make_run_and_graph(tag: str, is_current: bool) -> GraphRevision:
        run = ExtractionRun(mapping_revision_id=rev.id, status="SUCCESS")
        session.add(run)
        session.flush()
        graph = GraphRevision(run_id=run.id, is_current=is_current, publishable=True)
        session.add(graph)
        session.flush()
        session.add(
            EntityIdentity(
                graph_revision_id=graph.id,
                iri="https://e/a",
                type_iri="https://example.org/Person",
                row_key="a",
                attrs={},
            )
        )
        session.add(
            GraphTriple(
                graph_revision_id=graph.id,
                subject="https://e/a",
                predicate="knows",
                object_="https://e/a",
            )
        )
        return graph

    _v1 = make_run_and_graph("v1/", is_current=False)
    v2 = make_run_and_graph("v2/", is_current=True)
    session.add(
        EntityIdentity(
            graph_revision_id=v2.id,
            iri="https://e/v2b",
            type_iri="https://example.org/Person",
            row_key="b",
            attrs={},
        )
    )
    session.add(
        GraphTriple(
            graph_revision_id=v2.id,
            subject="https://e/a",
            predicate="knows",
            object_="https://e/v2b",
        )
    )
    session.flush()
    return _v1, v2


def test_graph_diff_reports_set_differences(
    client: TestClient, session: Session
) -> None:
    v1, v2 = _setup_graph(session)
    session.commit()
    response = client.get(f"/api/v1/extraction/graph/{v1.id}/diff/{v2.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["entities_added"] == ["https://e/v2b"]
    assert data["entities_removed"] == []
    assert data["triple_added_count"] == 1
    assert data["triple_removed_count"] == 0
    assert data["triples_added"][0]["object"] == "https://e/v2b"
    assert data["truncated"] is False


def test_shortest_path_finds_and_misses(client: TestClient, session: Session) -> None:
    v1, v2 = _setup_graph(session)
    session.add(
        GraphTriple(
            graph_revision_id=v2.id,
            subject="https://e/v2b",
            predicate="knows",
            object_="https://e/v2c",
        )
    )
    session.add(
        EntityIdentity(
            graph_revision_id=v2.id,
            iri="https://e/v2c",
            type_iri="https://example.org/Person",
            row_key="c",
            attrs={},
        )
    )
    session.commit()
    found = client.get(
        f"/api/v1/extraction/graph/{v2.id}/path",
        params={"from": "https://e/a", "to": "https://e/v2c", "max_hops": 2},
    ).json()
    assert found["found"] is True
    assert found["hops"] == 2
    assert found["nodes"][0] == "https://e/a"
    missed = client.get(
        f"/api/v1/extraction/graph/{v1.id}/path",
        params={"from": "https://e/a", "to": "https://e/missing", "max_hops": 2},
    ).json()
    assert missed["found"] is False
    assert missed["nodes"] == []


def _add_entity_resource(
    session: Session, ns: Namespace, name: str, kind: str, payload_extra: dict
) -> ModelResource:
    res = ModelResource(
        kind=kind, name=name, iri=f"https://example.org/{name}", namespace_id=ns.id
    )
    session.add(res)
    session.flush()
    session.add(
        ResourceRevision(
            resource_id=res.id,
            revision=1,
            payload=_snapshot_payload(name, res.iri, kind, **payload_extra),
            checksum="x",
        )
    )
    session.flush()
    return res


def _setup_ontology_for_recommendation(
    session: Session, onto_name: str, resource_suffix: str
) -> Ontology:
    """结构相同、命名不同的本体（改名不变性验证用）。"""
    ns = session.query(Namespace).filter_by(prefix="ex").one_or_none()
    if ns is None:
        ns = Namespace(prefix="ex", iri="https://example.org/", protected=True)
        session.add(ns)
        session.flush()
    onto = Ontology(
        name=onto_name,
        iri=f"https://example.org/{onto_name}#",
        status="PUBLISHED",
        current_revision=1,
    )
    session.add(onto)
    session.flush()

    company = _add_entity_resource(
        session, ns, f"Company{resource_suffix}", "ENTITY", {"datatype_props": []}
    )
    person = _add_entity_resource(
        session, ns, f"Person{resource_suffix}", "ENTITY", {"datatype_props": []}
    )
    holding = _add_entity_resource(
        session,
        ns,
        f"Holding{resource_suffix}",
        "ASSOC",
        {
            "resource_refs": [{"target_id": 0, "role": "assoc_attribute"}],
            "datatype_props": [
                {
                    "role": "assoc_attribute",
                    "name": "pct",
                    "iri": f"https://example.org/pct{resource_suffix}",
                    "datatype": "decimal",
                    "nullable": False,
                }
            ],
        },
    )
    # 自引用关系：公司属于公司
    owns = _add_entity_resource(
        session,
        ns,
        f"Owns{resource_suffix}",
        "OBJECT_PROP",
        {
            "definition_i18n": {},
            "resource_refs": [
                {"target_id": company.id, "role": "relation_domain"},
                {"target_id": company.id, "role": "relation_range"},
            ],
            "object_prop": {
                "owl": {"transitive": True, "symmetric": False},
            },
        },
    )
    # 带度量关联关系：人持股公司（经 ASSOC）
    invests = _add_entity_resource(
        session,
        ns,
        f"Invests{resource_suffix}",
        "OBJECT_PROP",
        {
            "definition_i18n": {},
            "resource_refs": [
                {"target_id": person.id, "role": "relation_domain"},
                {"target_id": holding.id, "role": "relation_range"},
            ],
            "object_prop": {"owl": {}},
        },
    )
    session.flush()
    onto_rev = OntologyRevision(
        ontology_id=onto.id,
        revision=1,
        ref_domains=[],
        ref_types=[company.id, person.id, holding.id, owns.id, invests.id],
        rules=[],
        resource_versions={
            str(company.id): 1,
            str(person.id): 1,
            str(holding.id): 1,
            str(owns.id): 1,
            str(invests.id): 1,
        },
    )
    session.add(onto_rev)
    session.flush()
    return onto


def _graph_for_ontology(session: Session, onto: Ontology) -> GraphRevision:
    mapping = Mapping(name=f"m-{onto.name}", ontology_id=onto.id)
    session.add(mapping)
    session.flush()
    rev = MappingRevision(mapping_id=mapping.id, revision=1, onto_version=1)
    session.add(rev)
    session.flush()
    run = ExtractionRun(mapping_revision_id=rev.id, status="SUCCESS")
    session.add(run)
    session.flush()
    graph = GraphRevision(run_id=run.id, is_current=False, publishable=True)
    session.add(graph)
    session.flush()
    session.add(
        EntityIdentity(
            graph_revision_id=graph.id,
            iri="https://e/x",
            type_iri="https://example.org/Company1",
            row_key="x",
            attrs={},
        )
    )
    session.flush()
    return graph


def test_layout_recommendation_is_rename_invariant(
    client: TestClient, session: Session
) -> None:
    """IRI/名称不同但语义相同的本体 → 相同形态推荐。"""
    onto_a = _setup_ontology_for_recommendation(session, "oa", "A")
    graph_a = _graph_for_ontology(session, onto_a)
    onto_b = _setup_ontology_for_recommendation(session, "ob", "ZZZ")
    graph_b = _graph_for_ontology(session, onto_b)
    session.commit()

    rec_a = client.get(
        f"/api/v1/extraction/graph/{graph_a.id}/layout-recommendations"
    ).json()
    rec_b = client.get(
        f"/api/v1/extraction/graph/{graph_b.id}/layout-recommendations"
    ).json()
    ids_a = [r["layout_id"] for r in rec_a["recommendations"]]
    ids_b = [r["layout_id"] for r in rec_b["recommendations"]]
    assert ids_a == ids_b
    # 结构信号（自引用 + 传递 + 带度量关联）必须触发树/穿透形态
    assert "org_tree" in ids_a
    assert "equity_tree" in ids_a
    assert rec_a["signals"]["transitive"] is True
    assert rec_a["signals"]["measured_link"]


def test_view_template_crud_and_staleness(client: TestClient, session: Session) -> None:
    onto = _setup_ontology_for_recommendation(session, "ot", "T")
    _graph_for_ontology(session, onto)
    session.commit()
    created = client.post(
        "/api/v1/view-templates",
        json={
            "name_i18n": {"zh-CN": "股权穿透默认视图", "en-US": "Equity default"},
            "layout_id": "equity_tree",
            "config": {"threshold": 5},
            "ontology_id": onto.id,
            "ontology_revision": 1,
        },
    )
    assert created.status_code == 201
    template = created.json()
    assert template["stale"] is False

    # 本体发布新版本 → 模板失效
    onto.current_revision = 2
    session.add(
        OntologyRevision(
            ontology_id=onto.id,
            revision=2,
            ref_domains=[],
            ref_types=[],
            rules=[],
            resource_versions={},
        )
    )
    session.commit()
    listed = client.get(
        "/api/v1/view-templates", params={"ontology_id": onto.id}
    ).json()
    assert listed["items"][0]["stale"] is True

    deleted = client.delete(f"/api/v1/view-templates/{template['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/view-templates/{template['id']}").status_code == 404


def test_reverse_trace_from_source_row(client: TestClient, session: Session) -> None:
    _, v2 = _setup_graph(session)
    session.add(
        FactEvidence(
            graph_revision_id=v2.id,
            subject="https://e/a",
            predicate="knows",
            object_="https://e/v2b",
            source_id=1,
            table_name="hr_person",
            row_key="9",
            columns=["name"],
            run_id=v2.run_id,
            evidence_type="RELATION",
        )
    )
    session.commit()
    data = client.get(
        "/api/v1/extraction/evidence/trace/reverse",
        params={"source_id": 1, "table": "hr_person", "row_key": "9"},
    ).json()
    assert data["row_key"] == "9"
    assert len(data["facts"]) == 1
    assert data["entities"] == ["https://e/a", "https://e/v2b"]


def test_a05_flags_rule_drift_and_a06_flags_missing_template_members(
    client: TestClient, session: Session
) -> None:
    from app.domain.validation_service import run_ontology_validation

    onto = _setup_ontology_for_recommendation(session, "ov", "V")
    # 钉扎一条随后被改的规则
    rule = Rule(
        identifier="R1",
        name_i18n={"zh-CN": "r", "en-US": "r"},
        category="c",
        source_kind="ENTERPRISE",
        source_reference="S",
        target_iri="https://example.org/CompanyV",
        severity="VIOLATION",
        language="DATA",
        expression=json.dumps({"op": "acyclic", "edge": "x"}),
        execution="AUTO",
        positive_example="",
        negative_example="",
        revision=2,
    )
    session.add(rule)
    session.flush()
    session.add(
        OntologyRuleRef(ontology_id=onto.id, rule_id=rule.id, pinned_revision=1)
    )
    # 模板：引用了本体未保留的资源
    template = AssemblyTemplate(
        name="tpl",
        label_i18n={"zh-CN": "t", "en-US": "t"},
        source="S",
        basis="B",
        builtin=False,
        payload={"resources": [{"resource_id": 999999, "pinned_revision": 1}]},
    )
    session.add(template)
    session.flush()
    onto.template_id = template.id
    session.flush()

    report = run_ontology_validation(session, onto.id)
    session.commit()
    states = {c.check_code: c.state for c in report.results}
    assert states["A05"] == "VIOLATION"
    assert states["A06"] == "VIOLATION"
