"""抽取引擎集成测试（H-32）。

必测断言：
- 幂等性：同配置重跑 IRI 集合一致
- 失败保护：零产出判 FAILED，is_current 不动
- 结果集切换：历史成功运行可切回
- 证据追溯：任一事实反查到来源表/行键/字段/运行批次
- 三模式：FK / JUNCTION / ASSOCIATIVE
"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.extraction_service import (
    get_current_graph,
    get_evidence,
    list_entity_identities,
    list_triples,
    start_run,
    switch_current,
)
from app.domain.mapping_compiler import _apply_transform  # noqa: F401
from app.domain.mapping_service import (
    create_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.source_service import create_datasource
from app.models.domain import Ontology, OntologyRevision
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
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def _make_source(path: str) -> None:
    """建一个覆盖三类关系结构的源库。"""
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
                "CREATE TABLE pm_project_member ("
                "id INTEGER PRIMARY KEY, "
                "project_id INTEGER NOT NULL, "
                "member_id INTEGER NOT NULL, "
                "role TEXT, "
                "FOREIGN KEY (project_id) REFERENCES pm_project(id), "
                "FOREIGN KEY (member_id) REFERENCES hr_employee(id))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO enterprise (id, name, credit_code) VALUES "
                "(1001, '企业A', 'C001'), (1002, '企业B', 'C002')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO hr_employee (id, name, enterprise_id) VALUES "
                "(8001, '张三', 1001), (8002, '李四', 1002)"
            )
        )
        conn.execute(text("INSERT INTO ct_contract (id, code) VALUES (6001, 'HT-1')"))
        conn.execute(text("INSERT INTO pm_project (id, name) VALUES (7001, '项目X')"))
        conn.execute(
            text(
                "INSERT INTO ct_contract_project (contract_id, project_id) "
                "VALUES (6001, 7001)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO pm_project_member (id, project_id, member_id, role) "
                "VALUES (1, 7001, 8001, '项目经理')"
            )
        )
        conn.commit()


@pytest.fixture()
def session(tmp_path):
    url = f"sqlite:///{tmp_path}/kg.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = sf()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def source_db(tmp_path):
    path = str(tmp_path / "src.db")
    _make_source(path)
    yield path


def _setup_onto(session):
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
    return onto


def _setup_ds(session, source_db):
    ds = create_datasource(
        session,
        DatasourceCreate(name="ds1", kind="sqlite", params={"database": source_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    return ds


def _full_mapping(session, onto):
    """建一个覆盖三模式的全量映射并发布。"""
    m = create_mapping(session, MappingCreate(name="full", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="Enterprise",
                    table="enterprise",
                    field_maps=[
                        FieldMap(
                            target_attr="name",
                            source_field="name",
                        )
                    ],
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
                ),
                RelMapCreate(
                    relation_type="contract_project",
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
                RelMapCreate(
                    relation_type="participates",
                    mode=RelMode.ASSOCIATIVE,
                    table="pm_project_member",
                    source=RelEndpointSpec(
                        field="project_id",
                        ref_table="pm_project",
                        ref_field="id",
                    ),
                    target=RelEndpointSpec(
                        field="member_id",
                        ref_table="hr_employee",
                        ref_field="id",
                    ),
                    attributes=[{"attr": "role", "field": "role"}],
                ),
            ],
        ),
        if_match=0,
    )
    session.commit()
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()
    return rev


def test_idempotent_rerun(session, source_db):
    """幂等性：同配置重跑，IRI 集合一致。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    rev = _full_mapping(session, onto)

    run1 = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr1 = get_current_graph(session)
    assert gr1 is not None
    assert gr1.is_current is True

    entities1, _ = list_entity_identities(session, gr1.id)
    iri_set_1 = {e.iri for e in entities1}
    triples1, _ = list_triples(session, gr1.id)
    triple_set_1 = {(t.subject, t.predicate, t.object_) for t in triples1}

    # 第二次运行
    run2 = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr2 = get_current_graph(session)
    assert gr2 is not None
    assert gr2.id != gr1.id
    assert gr2.is_current is True
    assert gr1.is_current is False

    entities2, _ = list_entity_identities(session, gr2.id)
    iri_set_2 = {e.iri for e in entities2}
    triples2, _ = list_triples(session, gr2.id)
    triple_set_2 = {(t.subject, t.predicate, t.object_) for t in triples2}

    # 幂等核心断言：IRI 集合一致
    assert iri_set_1 == iri_set_2
    assert triple_set_1 == triple_set_2

    # 两次运行都成功
    assert run1.status == RunResult.SUCCESS
    assert run2.status == RunResult.SUCCESS
    # 指纹一致（同配置同产出）
    assert run1.fingerprint == run2.fingerprint


def test_failure_protection_zero_output(session, source_db):
    """失败保护：零产出判 FAILED，is_current 不动。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)

    # 先跑一次成功的，建立 current
    rev = _full_mapping(session, onto)
    start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr_ok = get_current_graph(session)
    assert gr_ok is not None
    assert gr_ok.is_current is True

    # 再建一个映射到不存在的表，产生零产出
    m2 = create_mapping(session, MappingCreate(name="empty", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m2.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="Ghost",
                    table="ghost_table",
                    field_maps=[FieldMap(target_attr="x", source_field="x")],
                    key_fields=["id"],
                )
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    rev2 = publish_mapping(session, m2.id, if_match=0)
    session.commit()

    run_fail = start_run(session, rev2.id, ds.id, "https://example.org/kg/")
    session.commit()

    # 零产出判 FAILED
    assert run_fail.status == RunResult.FAILED
    # is_current 不动：还是成功运行的那个
    gr_after = get_current_graph(session)
    assert gr_after is not None
    assert gr_after.id == gr_ok.id


def test_result_set_switch(session, source_db):
    """结果集切换：历史成功运行可切回。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    rev = _full_mapping(session, onto)

    start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr1 = get_current_graph(session)
    assert gr1 is not None

    start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr2 = get_current_graph(session)
    assert gr2 is not None
    assert gr2.id != gr1.id

    # 切回第一次
    switched = switch_current(session, gr1.id)
    session.commit()
    assert switched.id == gr1.id
    assert switched.is_current is True
    assert gr2.is_current is False

    gr_now = get_current_graph(session)
    assert gr_now is not None
    assert gr_now.id == gr1.id


def test_evidence_traceability(session, source_db):
    """证据追溯：任一事实反查到来源表/行键/字段/运行批次。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    rev = _full_mapping(session, onto)

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr = get_current_graph(session)
    assert gr is not None

    # 取一条 FK 关系三元组
    triples, _ = list_triples(session, gr.id)
    fk_triples = [t for t in triples if t.predicate == "works_for"]
    assert len(fk_triples) >= 1
    t = fk_triples[0]

    # 反查证据
    ev = get_evidence(session, t.subject, t.predicate, t.object_)
    assert len(ev) >= 1
    e = ev[0]
    assert e.run_id == run.id
    assert e.table_name == "hr_employee"
    assert e.evidence_type == "RELATION"
    assert "enterprise_id" in e.columns


def test_cannot_run_draft(session, source_db):
    """草稿 revision（revision=0）不能运行。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="draft", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="n", source_field="name")],
                    key_fields=["id"],
                )
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    # 草稿 revision 的 id 需要查
    from app.models.data_access import MappingRevision

    draft_rev = (
        session.query(MappingRevision)
        .filter(MappingRevision.mapping_id == m.id, MappingRevision.revision == 0)
        .first()
    )
    with pytest.raises(KGError) as exc:
        start_run(session, draft_rev.id, ds.id)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_three_relation_modes(session, source_db):
    """三模式：FK / JUNCTION / ASSOCIATIVE 各产出三元组。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    rev = _full_mapping(session, onto)
    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    assert run.status == RunResult.SUCCESS
    gr = get_current_graph(session)
    assert gr is not None

    triples, _ = list_triples(session, gr.id)
    predicates = {t.predicate for t in triples}
    assert "works_for" in predicates  # FK
    assert "contract_project" in predicates  # JUNCTION
    assert "participates" in predicates  # ASSOCIATIVE

    # 计数校验
    assert run.counts["entity_count"] >= 2
    assert run.counts["triple_count"] >= 3
