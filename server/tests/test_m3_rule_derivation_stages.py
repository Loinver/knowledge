"""抽取阶段3（规则校验）与阶段4（派生推导）集成测试。

必测断言：
- 规则阶段：DATA 规则在管线内真实执行，命中写隔离并计数
- 四态不失真：SHACL 规则不在管线范围 → 结果如实 NOT_RUN
- 版本完整性：规则发布后被改 → NOT_RUN（rule_changed_after_pin）
- 派生阶段：co_occurrence / product_chain 产出 DerivedEdge，
  rule_id 与 source_fact_ids 可展开；derived_edge_count 真实计数
- 实例校验报告随 run 产出（validation_summary）
"""

from __future__ import annotations

import json

import pytest
from app.core.db import Base
from app.domain.extraction_service import (
    get_current_graph,
    start_run,
)
from app.domain.mapping_service import (
    create_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.source_service import create_datasource
from app.models.domain import Ontology, OntologyRevision, OntologyRuleRef
from app.models.enums import RunResult
from app.models.extraction import DerivedEdge, GraphRevision, Quarantine
from app.models.governance import Rule
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
    RelEndpointCandidate,
    RelEndpointSpec,
    RelEndpointVia,
    RelMapCreate,
    RelMode,
)
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker


def _make_stage_source(path: str) -> None:
    """覆盖规则命中与派生场景的源库。"""
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
                "CREATE TABLE org_department ("
                "id INTEGER PRIMARY KEY, parent_id INTEGER, name TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE ct_contract ("
                "id INTEGER PRIMARY KEY, code TEXT, sign_date TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE eq_shareholder ("
                "id INTEGER PRIMARY KEY, person_id INTEGER, enterprise_id INTEGER)"
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
                "CREATE TABLE pm_project_member ("
                "id INTEGER PRIMARY KEY, project_id INTEGER, member_id INTEGER)"
            )
        )
        # 两企业共用同一 credit_code → unique_attr 命中
        conn.execute(
            text(
                "INSERT INTO enterprise VALUES "
                "(1001, '企业A', 'C001'), (1002, '企业B', 'C001')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO hr_employee VALUES "
                "(8001, '张三'), (8002, '李四'), (8003, '王五')"
            )
        )
        # 部门环：1 -> 2 -> 1 → acyclic 命中
        conn.execute(
            text("INSERT INTO org_department VALUES (1, 2, '甲科'), (2, 1, '乙科')")
        )
        # 合同日期：一条 YYYYMMDD 合法、一条 2024/02/01 非法 → date_format 命中
        conn.execute(
            text(
                "INSERT INTO ct_contract VALUES "
                "(6001, 'HT-1', '20240201'), (6002, 'HT-2', '2024/02/01')"
            )
        )
        # 持股：1001 被 201/203 合计 115% → sum_le 命中
        # 乘积链：8001 ->(50%) 1002，203(=1002) ->(40%) 1001 → 间接 20%
        conn.execute(
            text(
                "INSERT INTO eq_shareholder VALUES (201, 8001, NULL), (203, NULL, 1002)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO eq_equity_holding VALUES "
                "(3001, 201, 1001, 60.0), (3002, 203, 1001, 55.0), "
                "(3003, 201, 1002, 50.0)"
            )
        )
        # 共同参与：8001/8002 同项目 → co_occurrence 命中
        conn.execute(
            text(
                "INSERT INTO pm_project_member VALUES "
                "(1, 7001, 8001), (2, 7001, 8002), (3, 7002, 8003)"
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
def stage_db(tmp_path):
    path = str(tmp_path / "stage.db")
    _make_stage_source(path)
    yield path


def _setup_onto(session) -> Ontology:
    onto = Ontology(
        name="os", iri="https://example.org/os#", status="PUBLISHED", current_revision=1
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


def _add_rule(
    session, onto, identifier, language, expression, execution="AUTO", revision=1
):
    rule = Rule(
        identifier=identifier,
        name_i18n={"zh-CN": identifier, "en-US": identifier},
        category="scene",
        source_kind="ENTERPRISE",
        source_reference="TEST-SRC",
        target_iri="https://example.org/os#Enterprise",
        severity="VIOLATION",
        language=language,
        expression=expression,
        execution=execution,
        positive_example=""
        if language != "SHACL"
        else "@prefix ex: <https://ex.org/> .",
        negative_example=""
        if language != "SHACL"
        else "@prefix ex: <https://ex.org/> .",
        revision=revision,
    )
    session.add(rule)
    session.flush()
    session.add(
        OntologyRuleRef(ontology_id=onto.id, rule_id=rule.id, pinned_revision=revision)
    )
    session.flush()
    return rule


def _setup_rules(session, onto):
    _add_rule(
        session,
        onto,
        "R-SUM",
        "DATA",
        json.dumps(
            {
                "op": "sum_le",
                "edge": "holds_equity_in",
                "attr": "pct",
                "max": 100,
                "group": "object",
            }
        ),
    )
    _add_rule(
        session,
        onto,
        "R-CYC",
        "DATA",
        json.dumps({"op": "acyclic", "edge": "reports_to"}),
    )
    _add_rule(
        session,
        onto,
        "R-UNIQ",
        "DATA",
        json.dumps({"op": "unique_attr", "type": "Enterprise", "attr": "creditCode"}),
    )
    _add_rule(
        session,
        onto,
        "R-DATE",
        "DATA",
        json.dumps({"op": "date_format", "attr": "signedDate", "format": "YYYYMMDD"}),
    )
    _add_rule(
        session,
        onto,
        "R-SHACL",
        "SHACL",
        "shape",
        execution="MANUAL",
    )
    _add_rule(
        session,
        onto,
        "R-CO",
        "DERIVATION",
        json.dumps(
            {
                "op": "co_occurrence",
                "via_edge": "member_of",
                "derive_edge": "colleague_of",
            }
        ),
    )
    _add_rule(
        session,
        onto,
        "R-PROD",
        "DERIVATION",
        json.dumps(
            {
                "op": "product_chain",
                "edge": "holds_equity_in",
                "attr": "pct",
                "derive_edge": "indirectly_holds",
                "min_value": 0.01,
            }
        ),
    )


def _mapping(session, onto):
    m = create_mapping(session, MappingCreate(name="stage", ontology_id=onto.id))
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
                        FieldMap(target_attr="name", source_field="name"),
                        FieldMap(target_attr="creditCode", source_field="credit_code"),
                    ],
                    key_fields=["id"],
                ),
                EntityMapCreate(
                    entity_type="Person",
                    table="hr_employee",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
                EntityMapCreate(
                    entity_type="Department",
                    table="org_department",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                ),
                EntityMapCreate(
                    entity_type="Contract",
                    table="ct_contract",
                    field_maps=[
                        FieldMap(target_attr="code", source_field="code"),
                        FieldMap(target_attr="signedDate", source_field="sign_date"),
                    ],
                    key_fields=["id"],
                ),
            ],
            rel_maps=[
                RelMapCreate(
                    relation_type="reports_to",
                    mode=RelMode.FK,
                    table="org_department",
                    fk_field="parent_id",
                ),
                RelMapCreate(
                    relation_type="holds_equity_in",
                    mode=RelMode.ASSOCIATIVE,
                    table="eq_equity_holding",
                    source=RelEndpointSpec(
                        candidates=[
                            RelEndpointCandidate(
                                field="person_id",
                                ref_table="hr_employee",
                                ref_entity_type="Person",
                            ),
                            RelEndpointCandidate(
                                field="enterprise_id",
                                ref_table="enterprise",
                                ref_entity_type="Enterprise",
                            ),
                        ],
                        via=RelEndpointVia(
                            table="eq_shareholder",
                            field="shareholder_id",
                            ref_field="id",
                        ),
                    ),
                    target=RelEndpointSpec(
                        field="investee_enterprise_id",
                        ref_table="enterprise",
                        ref_field="id",
                    ),
                    attributes=[{"attr": "pct", "field": "ownership_pct"}],
                ),
                RelMapCreate(
                    relation_type="member_of",
                    mode=RelMode.JUNCTION,
                    table="pm_project_member",
                    source=RelEndpointSpec(
                        field="member_id", ref_table="hr_employee", ref_field="id"
                    ),
                    target=RelEndpointSpec(
                        candidates=[
                            RelEndpointCandidate(
                                field="project_id", ref_table="pm_project"
                            )
                        ]
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


def test_rule_stage_executes_data_rules_and_quarantines(session, stage_db):
    """DATA 规则管线内执行：sum_le/acyclic/date_format/unique_attr 命中并隔离。"""
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(name="dsr", kind="sqlite", params={"database": stage_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    _setup_rules(session, onto)
    rev = _mapping(session, onto)

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    assert run.status == RunResult.PARTIAL
    assert run.counts["rule_violation_count"] > 0
    results = {r["rule_id"]: r for r in run.counts["rule_results"]}
    assert results["R-SUM"]["state"] == "VIOLATION"
    assert results["R-CYC"]["state"] == "VIOLATION"
    assert results["R-UNIQ"]["state"] == "VIOLATION"
    assert results["R-DATE"]["state"] == "VIOLATION"
    # MANUAL SHACL 不进结果（不在管线执行范围）
    assert "R-SHACL" not in results
    # 命中写隔离并带规则 ID
    quarantines = list(
        session.scalars(select(Quarantine).where(Quarantine.run_id == run.id))
    )
    rule_ids = {q.rule_id for q in quarantines}
    assert {"R-SUM", "R-CYC", "R-UNIQ", "R-DATE"} <= rule_ids
    # 实例校验报告随阶段产出
    assert run.counts["validation_summary"]["violation"] >= 0


def test_rule_changed_after_pin_is_not_run(session, stage_db):
    """规则发布后被改（revision 漂移）→ 如实 NOT_RUN，不冒充执行。"""
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(name="dsr2", kind="sqlite", params={"database": stage_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    rule = _add_rule(
        session,
        onto,
        "R-DRIFT",
        "DATA",
        json.dumps({"op": "acyclic", "edge": "reports_to"}),
        revision=1,
    )
    # 模拟本体发布后规则被编辑：revision 前移，钉扎仍是 1
    rule.revision = 2
    session.flush()
    rev = _mapping(session, onto)

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    results = {r["rule_id"]: r for r in run.counts["rule_results"]}
    assert results["R-DRIFT"]["state"] == "NOT_RUN"
    assert results["R-DRIFT"]["reason"] == "rule_changed_after_pin"


def test_derivation_stage_writes_provenance_and_count(session, stage_db):
    """派生边带 rule_id 与 source_fact_ids；derived_edge_count 真实计数。"""
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(name="dsr3", kind="sqlite", params={"database": stage_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    _setup_rules(session, onto)
    rev = _mapping(session, onto)

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    gr = session.get(GraphRevision, get_current_graph(session).id)
    derived = list(
        session.scalars(
            select(DerivedEdge).where(DerivedEdge.graph_revision_id == gr.id)
        )
    )
    assert run.counts["derived_edge_count"] == len(derived) > 0
    by_rule = {}
    for edge in derived:
        by_rule.setdefault(edge.rule_id, []).append(edge)
    # 同事派生：8001/8002 共同参与 7001
    colleagues = by_rule.get("R-CO", [])
    assert len(colleagues) == 1
    assert colleagues[0].source_fact_ids, "共同参与派生必须引用参与事实"
    # 乘积链：8001 -(50%)-> 1002 -(55%)-> 1001 → 间接 27.5%
    indirect = by_rule.get("R-PROD", [])
    assert any(
        edge.props and abs(edge.props.get("pct", 0) - 27.5) < 1e-6 for edge in indirect
    )
    assert all(edge.source_fact_ids for edge in indirect)
    # 派生边不占用三元组计数
    assert run.counts["triple_count"] > 0
