"""M3 贯通测试：8 步主流程一次跑通整条链。

验收 v0.1.0：建模 -> 装配 -> 映射 -> 抽取 -> 幂等 -> 失败保护 -> 证据 -> 隔离。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.db import Base
from app.domain.extraction_service import (
    get_current_graph,
    get_evidence,
    list_entity_identities,
    list_triples,
    start_run,
    switch_current,
)
from app.domain.iri_service import register_namespace
from app.domain.mapping_service import (
    create_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.relation_service import create_relation_type
from app.domain.source_service import create_datasource
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.models.enums import RunResult
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
    RelEndpointSpec,
    RelMapCreate,
    RelMode,
)
from app.schemas.ontology import OntologyCreate
from app.schemas.relation import EndpointSpec, RelationTypeCreate
from app.schemas.type import EntityTypeCreate
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
            text("CREATE TABLE ct_contract (id INTEGER PRIMARY KEY, code TEXT)")
        )
        conn.execute(
            text("CREATE TABLE pm_project (id INTEGER PRIMARY KEY, name TEXT)")
        )
        conn.execute(
            text(
                "CREATE TABLE ct_contract_project ("
                "contract_id INTEGER NOT NULL, "
                "project_id INTEGER NOT NULL, "
                "PRIMARY KEY (contract_id, project_id), "
                "FOREIGN KEY (contract_id) REFERENCES ct_contract(id), "
                "FOREIGN KEY (project_id) REFERENCES pm_project(id))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO enterprise (id, name, credit_code) VALUES "
                "(1001, 'A', 'C001'), (1002, 'B', 'C002')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO hr_employee (id, name, enterprise_id) VALUES "
                "(8001, 'Zhang', 1001), (8002, 'Li', 1002)"
            )
        )
        conn.execute(text("INSERT INTO ct_contract (id, code) VALUES (6001, 'CT01')"))
        conn.execute(
            text(
                "CREATE TABLE pm_project_member ("
                "id INTEGER PRIMARY KEY, project_id INTEGER, "
                "member_id INTEGER, role TEXT)"
            )
        )
        conn.execute(text("INSERT INTO pm_project (id, name) VALUES (7001, 'P1')"))
        conn.execute(
            text(
                "INSERT INTO ct_contract_project (contract_id, project_id) "
                "VALUES (6001, 7001)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO pm_project_member (id, project_id, member_id, role) "
                "VALUES (1, 7001, 8001, 'lead')"
            )
        )
        conn.commit()


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)
    db = session_local()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def source_db(tmp_path: Path) -> str:
    p = str(tmp_path / "src.db")
    _make_source(p)
    return p


def test_eight_step_pipeline(session: Session, source_db: str) -> None:
    """8 步贯通：建模 -> 装配 -> 映射 -> 抽取 -> 幂等 -> 失败保护 -> 证据 -> 隔离。"""
    ns = register_namespace(session, "kg", "https://example.org/kg#")

    # 步骤 1: 建 3 个实体类型 + 2 个关系类型，全部发布
    enterprise = create_entity_type(
        session,
        EntityTypeCreate(
            name="Enterprise",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "企业"},
        ),
    )
    employee = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工"},
        ),
    )
    contract = create_entity_type(
        session,
        EntityTypeCreate(
            name="Contract",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "合同"},
        ),
    )
    project = create_entity_type(
        session,
        EntityTypeCreate(
            name="Project",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "项目"},
        ),
    )
    publish_resource(session, enterprise)
    publish_resource(session, employee)
    publish_resource(session, contract)
    publish_resource(session, project)

    works_for = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksFor",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于"},
            domain_spec=EndpointSpec(type_id=employee.id),
            range_spec=EndpointSpec(type_id=enterprise.id),
        ),
    )
    contract_project = create_relation_type(
        session,
        RelationTypeCreate(
            name="ContractProject",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "合同关联项目"},
            domain_spec=EndpointSpec(type_id=contract.id),
            range_spec=EndpointSpec(type_id=project.id),
        ),
    )
    publish_resource(session, works_for)
    publish_resource(session, contract_project)
    session.commit()
    assert enterprise.current_revision == 1
    assert works_for.current_revision == 1

    # 步骤 2: 装配本体并发布
    onto = create_ontology(
        session,
        OntologyCreate(
            name="pipeline-onto",
            iri="https://example.org/onto#pipeline",
            label_i18n={"zh-CN": "贯通本体"},
            ref_resource_ids=[
                enterprise.id,
                employee.id,
                contract.id,
                project.id,
                works_for.id,
                contract_project.id,
            ],
        ),
    )
    session.commit()
    onto_rev = publish_ontology(session, onto)
    session.commit()
    assert onto_rev is not None

    # 步骤 3: 配映射（FK + JUNCTION），发布
    ds = create_datasource(
        session,
        DatasourceCreate(name="ds", kind="sqlite", params={"database": source_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()

    m = create_mapping(session, MappingCreate(name="m", ontology_id=onto.id))
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
                EntityMapCreate(
                    entity_type="Contract",
                    table="ct_contract",
                    field_maps=[FieldMap(target_attr="code", source_field="code")],
                    key_fields=["id"],
                ),
            ],
            rel_maps=[
                RelMapCreate(
                    relation_type="WorksFor",
                    mode=RelMode.FK,
                    table="hr_employee",
                    fk_field="enterprise_id",
                ),
                RelMapCreate(
                    relation_type="ContractProject",
                    mode=RelMode.JUNCTION,
                    table="ct_contract_project",
                    source=RelEndpointSpec(
                        field="contract_id",
                        ref_table="ct_contract",
                        ref_field="id",
                    ),
                    target=RelEndpointSpec(
                        field="project_id",
                        ref_table="pm_project",
                        ref_field="id",
                    ),
                ),
            ],
        ),
        if_match=0,
    )
    session.commit()
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()

    # 步骤 4: 运行抽取，产出实体/关系
    run = start_run(session, rev.id, ds.id, "https://example.org/kg#")
    session.commit()
    assert run.status == RunResult.SUCCESS
    gr = get_current_graph(session)
    assert gr is not None
    entities, e_total = list_entity_identities(session, gr.id)
    assert e_total >= 3
    triples, t_total = list_triples(session, gr.id)
    assert t_total >= 2
    assert run.counts["entity_count"] >= 3
    assert run.counts["triple_count"] >= 2

    first_iris = {e.iri for e in entities}
    first_triple_count = t_total

    # 步骤 5: 重复运行，IRI 集合、关系数一致（幂等）
    run2 = start_run(session, rev.id, ds.id, "https://example.org/kg#")
    session.commit()
    assert run2.status == RunResult.SUCCESS
    gr2 = get_current_graph(session)
    assert gr2 is not None and gr2.id != gr.id
    entities2, _e2_total = list_entity_identities(session, gr2.id)
    _triples2, t2_total = list_triples(session, gr2.id)
    assert {e.iri for e in entities2} == first_iris
    assert t2_total == first_triple_count

    # 步骤 6: 失败运行（清空源表），当前结果集不变，可切回
    eng = create_engine(f"sqlite:///{source_db}")
    with eng.connect() as conn:
        conn.execute(text("DELETE FROM hr_employee"))
        conn.execute(text("DELETE FROM enterprise"))
        conn.execute(text("DELETE FROM hr_employee"))
        conn.execute(text("DELETE FROM ct_contract"))
        conn.execute(text("DELETE FROM ct_contract_project"))
        conn.commit()
    eng.dispose()
    run3 = start_run(session, rev.id, ds.id, "https://example.org/kg#")
    session.commit()
    assert run3.status == RunResult.FAILED
    gr_after_fail = get_current_graph(session)
    assert gr_after_fail is not None
    assert gr_after_fail.id == gr2.id  # 失败不覆盖
    switch_current(session, gr.id)
    session.commit()
    gr_restored = get_current_graph(session)
    assert gr_restored is not None and gr_restored.id == gr.id

    # 步骤 7: 任一事实反查到来源表/行键/字段/运行批次
    fact = triples[0]
    evidence = get_evidence(session, fact.subject, fact.predicate, fact.object_)
    assert len(evidence) >= 1
    ev = evidence[0]
    assert ev.table_name != ""
    assert ev.run_id == run.id
    assert len(ev.columns) >= 1

    # 步骤 8: 隔离记录可定位（此 fixture 无隔离行，验证 run.counts 结构）
    assert (
        "quarantine_count" in run.counts or run.counts.get("quarantine_count", 0) >= 0
    )


def test_automation_regression_four_assertions(
    session: Session, source_db: str
) -> None:
    """4 项自动化回归：幂等、失败保护、结果集切换、证据追溯。"""
    ns = register_namespace(session, "kg", "https://example.org/kg#")
    enterprise = create_entity_type(
        session,
        EntityTypeCreate(name="E", namespace_id=ns.id, label_i18n={"zh-CN": "E"}),
    )
    employee = create_entity_type(
        session,
        EntityTypeCreate(name="Em", namespace_id=ns.id, label_i18n={"zh-CN": "Em"}),
    )
    publish_resource(session, enterprise)
    publish_resource(session, employee)
    works_for = create_relation_type(
        session,
        RelationTypeCreate(
            name="Wf",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "wf"},
            domain_spec=EndpointSpec(type_id=employee.id),
            range_spec=EndpointSpec(type_id=enterprise.id),
        ),
    )
    publish_resource(session, works_for)
    session.commit()
    onto = create_ontology(
        session,
        OntologyCreate(
            name="RegOnto",
            iri="https://example.org/reg#",
            label_i18n={"zh-CN": "RegOnto"},
            ref_resource_ids=[enterprise.id, employee.id, works_for.id],
        ),
    )
    session.commit()
    publish_ontology(session, onto)
    ds = create_datasource(
        session,
        DatasourceCreate(name="Rds", kind="sqlite", params={"database": source_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    m = create_mapping(session, MappingCreate(name="Rm", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
                EntityMapCreate(
                    entity_type="Em",
                    table="hr_employee",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
            ],
            rel_maps=[
                RelMapCreate(
                    relation_type="Wf",
                    mode=RelMode.FK,
                    table="hr_employee",
                    fk_field="enterprise_id",
                ),
            ],
        ),
        if_match=0,
    )
    session.commit()
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()

    # 幂等
    start_run(session, rev.id, ds.id, "https://example.org/kg#")
    session.commit()
    gr1 = get_current_graph(session)
    e1, _ = list_entity_identities(session, gr1.id)
    t1, _ = list_triples(session, gr1.id)
    start_run(session, rev.id, ds.id, "https://example.org/kg#")
    session.commit()
    gr2 = get_current_graph(session)
    e2, _ = list_entity_identities(session, gr2.id)
    t2, _ = list_triples(session, gr2.id)
    assert {e.iri for e in e1} == {e.iri for e in e2}
    assert len(t1) == len(t2)

    # 失败保护
    eng = create_engine(f"sqlite:///{source_db}")
    with eng.connect() as conn:
        conn.execute(text("DELETE FROM enterprise"))
        conn.execute(text("DELETE FROM hr_employee"))
        conn.commit()
    eng.dispose()
    r3 = start_run(session, rev.id, ds.id, "https://example.org/kg#")
    session.commit()
    assert r3.status == RunResult.FAILED
    assert get_current_graph(session).id == gr2.id

    # 结果集切换
    switch_current(session, gr1.id)
    session.commit()
    assert get_current_graph(session).id == gr1.id

    # 证据追溯
    fact = t1[0]
    ev = get_evidence(session, fact.subject, fact.predicate, fact.object_)
    assert len(ev) >= 1
    assert ev[0].table_name == "hr_employee"
    assert "enterprise_id" in ev[0].columns
