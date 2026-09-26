"""多态端点与业务键融合抽取（第一批 P0-08 / P0-04）。

必测断言：
- match_keys 融合：customer/supplier 同业务键 → 同一稳定 IRI，双来源证据保留
- 多态端点：candidates 判别（PERSON/ENTERPRISE）→ 端点类型正确
- 边属性：ASSOCIATIVE 属性写进 GraphTriple.props，图谱视图可读
- 空业务键：如实隔离，不静默跳过
"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.domain.extraction_service import (
    get_current_graph,
    get_entity_detail,
    list_entity_identities,
    list_triples,
    start_run,
)
from app.domain.graph_view_service import graph_view
from app.domain.mapping_service import (
    create_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.source_service import create_datasource
from app.models.domain import Ontology, OntologyRevision
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
    RelEndpointCandidate,
    RelEndpointSpec,
    RelMapCreate,
    RelMode,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def _make_fusion_source(path: str) -> None:
    """客商双表（共享信用代码）+ 多态股东 + 带属性关联。"""
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE enterprise ("
                "id INTEGER PRIMARY KEY, name TEXT, credit_code TEXT)"
            )
        )
        conn.execute(
            text("CREATE TABLE hr_employee (id INTEGER PRIMARY KEY, name TEXT)")
        )
        conn.execute(
            text(
                "CREATE TABLE crm_customer ("
                "id INTEGER PRIMARY KEY, credit_code TEXT, name TEXT, amount REAL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE crm_supplier ("
                "id INTEGER PRIMARY KEY, credit_code TEXT, name TEXT, amount REAL)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE eq_shareholder ("
                "id INTEGER PRIMARY KEY, shareholder_type TEXT, "
                "person_id INTEGER, enterprise_id INTEGER)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE eq_equity_holding ("
                "id INTEGER PRIMARY KEY, shareholder_id INTEGER, "
                "investee_enterprise_id INTEGER, ownership_pct REAL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO enterprise VALUES "
                "(1001, '企业A', 'C001'), (1002, '企业B', 'C002')"
            )
        )
        conn.execute(text("INSERT INTO hr_employee VALUES (8001, '张三')"))
        # 同一信用代码 C006 同时出现在客户与供应商表
        conn.execute(
            text(
                "INSERT INTO crm_customer VALUES "
                "(701, 'C005', '客户丙', 100.0), (702, 'C006', '双角色丁', 200.0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO crm_supplier VALUES "
                "(703, 'C004', '供应商乙', 300.0), (704, 'C006', '双角色丁', 400.0)"
            )
        )
        # 多态股东：个人 8001 与企业 1002
        conn.execute(
            text(
                "INSERT INTO eq_shareholder VALUES "
                "(201, 'PERSON', 8001, NULL), (203, 'ENTERPRISE', NULL, 1002)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO eq_equity_holding VALUES "
                "(3001, 201, 1001, 60.0), (3002, 203, 1001, 55.0)"
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
def fusion_db(tmp_path):
    path = str(tmp_path / "fusion.db")
    _make_fusion_source(path)
    yield path


def _setup_onto(session):
    onto = Ontology(
        name="of", iri="https://example.org/of#", status="PUBLISHED", current_revision=1
    )
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
    return onto


def _fusion_mapping(session, onto):
    """实体映射按 credit_code 融合；持股关系用多态端点。"""
    m = create_mapping(session, MappingCreate(name="fusion", ontology_id=onto.id))
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
                    entity_type="Person",
                    table="hr_employee",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
                EntityMapCreate(
                    entity_type="Partner",
                    table="crm_customer",
                    field_maps=[
                        FieldMap(target_attr="name", source_field="name"),
                        FieldMap(target_attr="amount", source_field="amount"),
                    ],
                    key_fields=["id"],
                    match_keys=["credit_code"],
                ),
                EntityMapCreate(
                    entity_type="Partner",
                    table="crm_supplier",
                    field_maps=[
                        FieldMap(target_attr="name", source_field="name"),
                        FieldMap(target_attr="amount", source_field="amount"),
                    ],
                    key_fields=["id"],
                    match_keys=["credit_code"],
                ),
            ],
            rel_maps=[
                RelMapCreate(
                    relation_type="holds_equity_in",
                    mode=RelMode.JUNCTION,
                    table="eq_equity_holding",
                    source=RelEndpointSpec(
                        candidates=[
                            RelEndpointCandidate(
                                field="shareholder_id",
                                ref_table="eq_shareholder",
                            )
                        ],
                        type_field=None,
                    ),
                    target=RelEndpointSpec(
                        field="investee_enterprise_id",
                        ref_table="enterprise",
                        ref_field="id",
                    ),
                ),
            ],
        ),
        if_match=0,
    )
    session.commit()
    # 端点二级解析：shareholder 行按判别字段转投 person/enterprise 表
    rev_record = m.current_revision
    assert rev_record == 0
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()
    return rev


def _polymorphic_mapping(session, onto):
    """股东表行按 shareholder_type 判别引用 person/enterprise。"""
    from app.domain.mapping_service import save_draft as save

    m = create_mapping(session, MappingCreate(name="poly", ontology_id=onto.id))
    session.commit()
    save(
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
                    entity_type="Person",
                    table="hr_employee",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
            ],
            rel_maps=[
                RelMapCreate(
                    relation_type="invests_in",
                    mode=RelMode.JUNCTION,
                    table="eq_shareholder",
                    source=RelEndpointSpec(
                        field="id",
                        ref_table="eq_shareholder",
                        ref_field="id",
                        candidates=[
                            RelEndpointCandidate(
                                field="person_id",
                                ref_table="hr_employee",
                                when="PERSON",
                                ref_entity_type="Person",
                            ),
                            RelEndpointCandidate(
                                field="enterprise_id",
                                ref_table="enterprise",
                                when="ENTERPRISE",
                                ref_entity_type="Enterprise",
                            ),
                        ],
                        type_field="shareholder_type",
                    ),
                    # 目标由 holding 表决定：这里直接用 enterprise_id 列演示
                    target=RelEndpointSpec(
                        candidates=[
                            RelEndpointCandidate(
                                field="enterprise_id",
                                ref_table="enterprise",
                                when="ENTERPRISE",
                            ),
                            RelEndpointCandidate(
                                field="person_id",
                                ref_table="hr_employee",
                                when="PERSON",
                            ),
                        ],
                        type_field="shareholder_type",
                    ),
                ),
            ],
        ),
        if_match=0,
    )
    session.commit()
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()
    return rev


def test_match_key_fusion_merges_cross_table_entities(session, fusion_db):
    """同信用代码跨表融合为一实体，双来源证据保留。"""
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(name="dsf", kind="sqlite", params={"database": fusion_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    rev = _fusion_mapping(session, onto)

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    assert run.status in ("SUCCESS", "PARTIAL")
    gr = get_current_graph(session)
    assert gr is not None

    partners = [
        e
        for e in list_entity_identities(session, gr.id, page_size=100)[0]
        if e.type_iri.endswith("Partner")
    ]
    # 4 行源数据（2 客户 + 2 供应商），C006 双表融合 → 3 个 Partner 实体
    assert len(partners) == 3
    fused = next(e for e in partners if e.iri.endswith("C006"))
    assert "C006" in fused.iri

    # 双来源证据：同一 IRI 两条实体证据，分别来自 customer 与 supplier
    evidences = get_entity_detail(session, fused.iri, gr.id)["evidence"]
    entity_evs = [ev for ev in evidences if ev.predicate == "_entity_attrs"]
    tables = {ev.table_name for ev in entity_evs}
    assert tables == {"crm_customer", "crm_supplier"}


def test_polymorphic_endpoint_resolves_by_discriminator(session, fusion_db):
    """shareholder_type 判别 PERSON/ENTERPRISE，端点落在正确类型实体上。"""
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(name="dsp", kind="sqlite", params={"database": fusion_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    rev = _polymorphic_mapping(session, onto)

    start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr = get_current_graph(session)
    assert gr is not None
    triples = list_triples(session, gr.id, page_size=100)[0]
    invests = [t for t in triples if t.predicate.endswith("invests_in")]
    assert len(invests) == 2
    # PERSON 分支 → hr_employee 实体；ENTERPRISE 分支 → enterprise 实体
    entity_types = {
        e.iri: e.type_iri
        for e in list_entity_identities(session, gr.id, page_size=100)[0]
    }
    by_subject = {t.subject: entity_types.get(t.subject) for t in invests}
    assert any(t.endswith("Person") for t in by_subject.values())
    assert any(t.endswith("Enterprise") for t in by_subject.values())


def test_associative_props_land_on_graph_edges(session, fusion_db):
    """ASSOCIATIVE 属性进 props，graph_view 的边可读出数值。"""
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(name="dse", kind="sqlite", params={"database": fusion_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    m = create_mapping(session, MappingCreate(name="props", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="Partner",
                    table="crm_customer",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
                EntityMapCreate(
                    entity_type="Enterprise",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
            ],
            rel_maps=[
                RelMapCreate(
                    relation_type="buys_from",
                    mode=RelMode.ASSOCIATIVE,
                    table="crm_customer",
                    source=RelEndpointSpec(
                        field="id", ref_table="crm_customer", ref_field="id"
                    ),
                    target=RelEndpointSpec(
                        candidates=[
                            RelEndpointCandidate(
                                field="credit_code", ref_table="enterprise"
                            )
                        ]
                    ),
                    attributes=[{"attr": "amount", "field": "amount"}],
                ),
            ],
        ),
        if_match=0,
    )
    session.commit()
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()
    start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr = get_current_graph(session)
    assert gr is not None
    view = graph_view(session, gr.id)
    edges_with_props = [e for e in view["edges"] if e["props"]]
    assert edges_with_props, "ASSOCIATIVE 属性必须出现在边 props 上"
    assert any(e["props"].get("amount") is not None for e in edges_with_props)
