"""资产层校验引擎集成测试（H-50）。"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import (
    add_ref,
    create_ontology,
    publish_ontology,
    remove_ref,
)
from app.domain.status_service import get_revision, publish_resource
from app.domain.type_service import create_entity_type
from app.domain.validation_service import run_ontology_validation
from app.models.domain import OntologyRevision
from app.models.enums import ResourceStatus, ValidationState
from app.models.resource import ModelResource
from app.models.validation import ValidationReport, ValidationResult
from app.schemas.ontology import OntologyCreate, OntologyRefAdd
from app.schemas.type import EntityTypeCreate
from app.semantics.backend import SemanticBackend
from app.semantics.backend import ValidationReport as SemanticValidationReport
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def session(tmp_path):
    url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = sf()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def ns(session):
    return register_namespace(session, "kg", "https://example.org/kg#")


@pytest.fixture()
def published_type(session, ns):
    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工", "en-US": "Employee"},
        ),
    )
    publish_resource(session, res)
    session.commit()
    return res


def _make_ontology(session, name="CoreOnto"):
    return create_ontology(
        session,
        OntologyCreate(
            name=name,
            iri=f"https://example.org/onto#{name}",
            label_i18n={"zh-CN": "核心本体"},
        ),
    )


def test_validation_all_pass_for_clean_ontology(session, published_type):
    """干净本体的校验：A01-A04 PASS、A05-A06 NA、A07 PASS、A08 NOT_RUN。"""
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    session.commit()
    report = run_ontology_validation(session, onto.id)
    session.commit()
    results = list(
        session.execute(
            select(ValidationResult).where(ValidationResult.report_id == report.id)
        ).scalars()
    )
    assert len(results) == 8
    by_code = {r.check_code: r.state for r in results}
    assert by_code["A01"] == ValidationState.PASS
    assert by_code["A02"] == ValidationState.PASS
    assert by_code["A03"] == ValidationState.PASS
    assert by_code["A04"] == ValidationState.PASS
    assert by_code["A05"] == ValidationState.NA
    assert by_code["A06"] == ValidationState.NA
    assert by_code["A07"] == ValidationState.PASS
    # 草稿本体无已发布版本可查 → A08 如实 NA（非适用），不是通过
    assert by_code["A08"] == ValidationState.NA
    assert report.summary["pass"] == 5
    assert report.summary["violation"] == 0
    assert report.summary["na"] == 3
    assert report.summary["not_run"] == 0


def test_a08_not_run_never_pass(session, published_type):
    """已发布本体但无推理器 → A08 NOT_RUN，绝不被当 PASS。"""
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    publish_ontology(session, onto)
    session.commit()
    report = run_ontology_validation(session, onto.id)
    session.commit()
    results = list(
        session.execute(
            select(ValidationResult).where(ValidationResult.report_id == report.id)
        ).scalars()
    )
    a08 = next(r for r in results if r.check_code == "A08")
    assert a08.state == ValidationState.NOT_RUN
    assert a08.state is not ValidationState.PASS


def test_a08_unpublished_ontology_is_na(
    session: Session, published_type: ModelResource
) -> None:
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    backend = Mock(spec=SemanticBackend)
    backend.has_full_reasoner.return_value = True
    report = run_ontology_validation(session, onto.id, backend=backend)
    a08 = next(result for result in report.results if result.check_code == "A08")
    assert a08.state == ValidationState.NA
    assert a08.message == "ontology not published"


def test_a08_runs_real_consistency_check(
    session: Session, published_type: ModelResource
) -> None:
    """A08 在有推理器时真实执行：引擎结论原样进四态，绝不改写。"""
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    publish_ontology(session, onto)
    session.commit()
    backend = Mock(spec=SemanticBackend)
    backend.has_full_reasoner.return_value = True
    backend.check_consistency.return_value = SemanticValidationReport(
        state=ValidationState.VIOLATION,
        conforms=False,
        results_text="owlrl OWL 2 RL consistency: 1 inconsistency(ies)",
        raw={"errors": ["Disjoint classes A and B have a common individual i"]},
    )
    report = run_ontology_validation(session, onto.id, backend=backend)
    a08 = next(result for result in report.results if result.check_code == "A08")
    assert a08.state == ValidationState.VIOLATION
    assert a08.detail is not None
    assert "Disjoint classes" in (a08.detail or {}).get("errors", [""])[0]
    backend.check_consistency.assert_called_once()


def test_a08_not_run_without_reasoner(
    session: Session, published_type: ModelResource
) -> None:
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    publish_ontology(session, onto)
    session.commit()
    report = run_ontology_validation(session, onto.id, backend=None)
    a08 = next(result for result in report.results if result.check_code == "A08")
    assert a08.state == ValidationState.NOT_RUN
    assert a08.message == "consistency reasoner not available"


def test_a02_violation_missing_zh_label(session, ns):
    """实体类型缺中文标签 → A02 VIOLATION。"""
    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"en-US": "Employee"},  # 缺 zh-CN
        ),
    )
    publish_resource(session, res)
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=res.id))
    session.commit()
    report = run_ontology_validation(session, onto.id)
    session.commit()
    results = list(
        session.execute(
            select(ValidationResult).where(ValidationResult.report_id == report.id)
        ).scalars()
    )
    a02 = next(r for r in results if r.check_code == "A02")
    assert a02.state == ValidationState.VIOLATION


def test_a07_violation_missing_namespace(session):
    """资源引用未注册命名空间 → A07 VIOLATION。"""
    from app.models.domain import OntologyResourceRef
    from app.models.enums import ResourceKind, ResourceStatus
    from app.models.resource import ModelResource

    onto = _make_ontology(session)
    res = ModelResource(
        kind=ResourceKind.ENTITY,
        name="Ghost",
        iri="https://ghost.org/x#Ghost",
        namespace_id=9999,  # 不存在
        label_i18n={"zh-CN": "幽灵"},
        status=ResourceStatus.PUBLISHED,
    )
    session.add(res)
    session.flush()
    session.add(OntologyResourceRef(ontology_id=onto.id, resource_id=res.id))
    session.commit()
    report = run_ontology_validation(session, onto.id)
    session.commit()
    results = list(
        session.execute(
            select(ValidationResult).where(ValidationResult.report_id == report.id)
        ).scalars()
    )
    a07 = next(r for r in results if r.check_code == "A07")
    assert a07.state == ValidationState.VIOLATION


def test_four_states_distinct_in_report(session, published_type):
    """报告里四态两两不等。"""
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    session.commit()
    report = run_ontology_validation(session, onto.id)
    session.commit()
    states_seen = set(report.summary.keys())
    assert states_seen == {"pass", "violation", "na", "not_run"}


def _report_content(report: ValidationReport) -> tuple[dict, list[tuple]]:
    return report.summary, [
        (r.check_code, r.state, r.focus_node, r.rule_id, r.detail, r.message)
        for r in report.results
    ]


def test_published_validation_ignores_resource_edits_and_live_membership(
    session: Session, published_type: ModelResource
) -> None:
    onto = _make_ontology(session)
    ref = add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    publish_ontology(session, onto)
    before = _report_content(run_ontology_validation(session, onto.id))

    published_type.status = ResourceStatus.DRAFT
    published_type.label_i18n = {"en-US": "Employee"}
    publish_resource(session, published_type)
    assert _report_content(run_ontology_validation(session, onto.id)) == before
    remove_ref(session, onto.id, ref.id)
    assert _report_content(run_ontology_validation(session, onto.id)) == before

    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    assert publish_ontology(session, onto) == 2
    report = run_ontology_validation(session, onto.id)
    assert report.target_revision == 2
    assert next(r.state for r in report.results if r.check_code == "A02") == (
        ValidationState.VIOLATION
    )


def test_draft_validation_tracks_live_resources_but_honors_explicit_pins(
    session: Session, published_type: ModelResource
) -> None:
    draft = _make_ontology(session, "Draft")
    pinned = _make_ontology(session, "Pinned")
    add_ref(session, draft.id, OntologyRefAdd(resource_id=published_type.id))
    add_ref(
        session,
        pinned.id,
        OntologyRefAdd(resource_id=published_type.id, pinned_revision=1),
    )
    before = _report_content(run_ontology_validation(session, pinned.id))
    published_type.status = ResourceStatus.DRAFT
    published_type.label_i18n = {"en-US": "Employee"}
    session.flush()
    report = run_ontology_validation(session, draft.id)
    assert next(r.state for r in report.results if r.check_code == "A02") == (
        ValidationState.VIOLATION
    )
    assert _report_content(run_ontology_validation(session, pinned.id)) == before
    publish_resource(session, published_type)
    assert _report_content(run_ontology_validation(session, pinned.id)) == before


def test_reopened_ontology_draft_uses_current_definitions(
    session: Session, published_type: ModelResource
) -> None:
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    publish_ontology(session, onto)
    onto.status = ResourceStatus.DRAFT
    published_type.label_i18n = {"en-US": "Employee"}
    session.flush()
    report = run_ontology_validation(session, onto.id)
    assert next(r.state for r in report.results if r.check_code == "A02") == (
        ValidationState.VIOLATION
    )


@pytest.mark.parametrize("missing", ["ontology", "resource", "structure"])
def test_published_validation_requires_its_frozen_snapshot(
    session: Session, published_type: ModelResource, missing: str
) -> None:
    onto = _make_ontology(session)
    add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    publish_ontology(session, onto)
    if missing == "ontology":
        revision = session.scalar(select(OntologyRevision))
        assert revision is not None
        session.delete(revision)
    elif missing == "resource":
        session.delete(get_revision(session, published_type.id, 1))
    else:
        resource_revision = get_revision(session, published_type.id, 1)
        resource_revision.payload = {
            key: value
            for key, value in resource_revision.payload.items()
            if key != "namespace"
        }
    session.flush()
    with pytest.raises(KGError) as exc:
        run_ontology_validation(session, onto.id)
    assert exc.value.code == (
        ErrorCode.VALIDATION_VIOLATION
        if missing == "structure"
        else ErrorCode.REVISION_NOT_FOUND
    )
    assert session.scalar(select(func.count()).select_from(ValidationReport)) == 0


def test_missing_draft_pin_does_not_use_current_resource(
    session: Session, published_type: ModelResource
) -> None:
    onto = _make_ontology(session)
    add_ref(
        session,
        onto.id,
        OntologyRefAdd(resource_id=published_type.id, pinned_revision=999),
    )
    with pytest.raises(KGError) as exc:
        run_ontology_validation(session, onto.id)
    assert exc.value.code == ErrorCode.REVISION_NOT_FOUND
    assert session.scalar(select(func.count()).select_from(ValidationReport)) == 0
