"""抽取阶段3（规则校验）与阶段4（派生推导）集成测试。

必测断言：
- 规则阶段：DATA 规则在管线内真实执行，命中写隔离并计数
- 四态不失真：冻结规则缺失/损坏 → NOT_RUN，不能回退当前正文
- 版本完整性：live 规则改版/模式切换不影响冻结 DATA/DERIVATION
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
from app.domain.ontology_service import publish_ontology, update_ontology
from app.domain.rule_service import delete_rule, update_rule
from app.domain.source_service import create_datasource
from app.models.domain import Ontology, OntologyRevision, OntologyRuleRef
from app.models.enums import RunResult
from app.models.extraction import DerivedEdge, GraphRevision, Quarantine
from app.models.governance import Rule
from app.schemas.datasource import DatasourceCreate
from app.schemas.governance import RuleCreate
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
from app.schemas.ontology import OntologyUpdate
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from test_m3_extraction import _setup_onto as _published_onto


def _semantic_expression(language: str) -> str:
    if language == "OWL":
        return (
            "<https://example.org/os#Enterprise> "
            "<http://www.w3.org/2002/07/owl#disjointWith> "
            "<https://example.org/os#Person> ."
        )
    return (
        "@prefix sh: <http://www.w3.org/ns/shacl#> . "
        "[] a sh:NodeShape; sh:targetClass <https://example.org/os#Enterprise>; "
        "sh:property [ sh:path <https://example.org/os#Enterprise/creditCode>; "
        "sh:minCount 1 ] ."
    )


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


def _setup_onto(session: Session) -> Ontology:
    return _published_onto(
        session,
        name="os",
        iri="https://example.org/os#",
        entity_props={
            "Enterprise": ("name", "creditCode"),
            "Person": ("name",),
            "Department": ("name",),
            "Contract": ("code", "signedDate"),
        },
    )


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
        else "<https://example.org/os#valid> a <https://example.org/os#Enterprise>; "
        '<https://example.org/os#Enterprise/creditCode> "VALID" .',
        negative_example=""
        if language != "SHACL"
        else "<https://example.org/os#invalid> a <https://example.org/os#Enterprise> .",
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
        _semantic_expression("SHACL"),
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


def _mapping(session, onto, *, publish_onto: bool = True):
    if publish_onto:
        publish_ontology(session, onto)
        session.commit()
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


def test_rule_changed_after_pin_still_executes_frozen_body(session, stage_db):
    """规则改版不改变旧映射冻结的 AUTO 执行正文。"""
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
    # 先真实发布规则快照，再模拟规则发布后编辑。
    onto_revision = publish_ontology(session, onto)
    session.commit()
    rule.revision = 2
    session.flush()
    rev = _mapping(session, onto, publish_onto=False)
    assert rev.onto_version == onto_revision

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    results = {r["rule_id"]: r for r in run.counts["rule_results"]}
    assert results["R-DRIFT"]["state"] == "VIOLATION"
    assert "reason" not in results["R-DRIFT"]


def test_auto_to_manual_keeps_frozen_auto_rule_execution(session, stage_db):
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="mode-drift", kind="sqlite", params={"database": stage_db}
        ),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    rule = _add_rule(
        session,
        onto,
        "R-MODE",
        "DATA",
        json.dumps({"op": "unique_attr", "type": "Enterprise", "attr": "creditCode"}),
    )
    rev = _mapping(session, onto)
    payload = RuleCreate.model_validate(rule, from_attributes=True).model_copy(
        update={"execution": "MANUAL"}
    )
    update_rule(session, rule.id, payload, revision=rule.revision)
    session.commit()

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    results = {item["rule_id"]: item for item in run.counts["rule_results"]}
    assert results["R-MODE"]["state"] == "VIOLATION"
    assert "reason" not in results["R-MODE"]


def test_old_mapping_uses_frozen_members_after_refs_are_replaced(session, stage_db):
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="ref-drift", kind="sqlite", params={"database": stage_db}
        ),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    _add_rule(
        session,
        onto,
        "R-FROZEN",
        "DATA",
        json.dumps({"op": "unique_attr", "type": "Enterprise", "attr": "creditCode"}),
    )
    rev = _mapping(session, onto)
    old_onto_version = rev.onto_version

    added_rule = Rule(
        identifier="R-ADDED",
        name_i18n={"zh-CN": "R-ADDED", "en-US": "R-ADDED"},
        category="scene",
        source_kind="ENTERPRISE",
        source_reference="TEST-SRC",
        target_iri="https://example.org/os#Enterprise",
        severity="VIOLATION",
        language="DATA",
        expression=json.dumps({"op": "acyclic", "edge": "reports_to"}),
        execution="AUTO",
        positive_example="",
        negative_example="",
        revision=1,
    )
    session.add(added_rule)
    session.flush()
    update_ontology(
        session,
        onto,
        OntologyUpdate(
            if_match=onto.current_revision,
            if_edit_match=onto.edit_revision,
            rule_ids=[added_rule.id],
        ),
    )
    new_onto_version = publish_ontology(session, onto)
    session.commit()

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    results = {item["rule_id"]: item for item in run.counts["rule_results"]}
    assert rev.onto_version == old_onto_version < new_onto_version
    assert set(results) == {"R-FROZEN"}
    assert results["R-FROZEN"]["state"] == "VIOLATION"
    assert run.cfg_snapshot["pins"]["rule_revisions"] == {"R-FROZEN": 1}


def test_frozen_rule_remains_executable_after_live_rule_delete(session, stage_db):
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="deleted-rule", kind="sqlite", params={"database": stage_db}
        ),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    rule = _add_rule(
        session,
        onto,
        "R-DELETED",
        "DATA",
        json.dumps({"op": "unique_attr", "type": "Enterprise", "attr": "creditCode"}),
    )
    rev = _mapping(session, onto)
    update_ontology(
        session,
        onto,
        OntologyUpdate(
            if_match=onto.current_revision,
            if_edit_match=onto.edit_revision,
            rule_ids=[],
        ),
    )
    session.commit()
    delete_rule(session, rule.id, revision=rule.revision)
    session.commit()

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    assert run.counts["rule_results"] == [
        {
            "rule_id": "R-DELETED",
            "language": "DATA",
            "state": "VIOLATION",
            "hits": 1,
            "quarantined": 1,
            "truncated": False,
        }
    ]


@pytest.mark.parametrize("legacy_snapshot", [None, {"id": 999, "revision": 1}])
def test_legacy_or_invalid_rule_body_is_not_run_without_live_fallback(
    session, stage_db, legacy_snapshot
):
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="legacy-rule", kind="sqlite", params={"database": stage_db}
        ),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    rule = _add_rule(
        session,
        onto,
        "R-LEGACY",
        "DATA",
        json.dumps({"op": "unique_attr", "type": "Enterprise", "attr": "creditCode"}),
    )
    rev = _mapping(session, onto)
    frozen = session.scalar(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == onto.id,
            OntologyRevision.revision == rev.onto_version,
        )
    )
    assert frozen is not None
    frozen_rules = [dict(item) for item in frozen.rules]
    frozen_rules[0]["snapshot"] = legacy_snapshot
    frozen.rules = frozen_rules
    update_rule(
        session,
        rule.id,
        RuleCreate.model_validate(rule, from_attributes=True).model_copy(
            update={"expression": json.dumps({"op": "acyclic", "edge": "reports_to"})}
        ),
        revision=rule.revision,
    )
    session.commit()

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()
    results = run.counts["rule_results"]
    assert results[0]["rule_id"] == "R-LEGACY"
    assert results[0]["state"] == "NOT_RUN"
    assert results[0]["reason"] == "rule_snapshot_unavailable"
    assert run.cfg_snapshot["pins"]["rule_revisions"] == {"R-LEGACY": 1}


@pytest.mark.parametrize("language", ["SHACL", "OWL"])
def test_corrupted_frozen_semantic_rule_is_reported_not_run(
    session: Session, stage_db: str, language: str
) -> None:
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="unexecuted", kind="sqlite", params={"database": stage_db}
        ),
    )
    session.commit()
    capture_metadata(session, ds.id)
    _add_rule(session, onto, "R-NOT-RUN", language, _semantic_expression(language))
    publish_ontology(session, onto)
    session.commit()
    rev = _mapping(session, onto, publish_onto=False)
    frozen = session.scalar(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == onto.id,
            OntologyRevision.revision == rev.onto_version,
        )
    )
    assert frozen is not None
    frozen.rules = [
        {**item, "snapshot": {**item["snapshot"], "expression": "{}"}}
        for item in frozen.rules
    ]
    session.flush()

    run = start_run(session, rev.id, ds.id, "https://example.org/kg/")
    session.commit()

    result = run.counts["rule_results"][0]
    assert result["rule_id"] == "R-NOT-RUN"
    assert result["language"] == language
    assert result["state"] == "NOT_RUN"
    assert result["hits"] == 0
    assert result["reason"]
    assert run.counts["derived_edge_count"] == 0


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
