"""资产层校验引擎集成测试（H-50）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import add_ref, create_ontology
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.domain.validation_service import run_ontology_validation
from app.models.enums import ValidationState
from app.models.validation import ValidationResult
from app.schemas.ontology import OntologyCreate, OntologyRefAdd
from app.schemas.type import EntityTypeCreate
from sqlalchemy import create_engine, select
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
    assert by_code["A08"] == ValidationState.NOT_RUN
    assert report.summary["pass"] == 5
    assert report.summary["violation"] == 0
    assert report.summary["na"] == 2
    assert report.summary["not_run"] == 1


def test_a08_not_run_never_pass(session, published_type):
    """A08 未接完整推理器 → NOT_RUN，绝不被当 PASS。"""
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
    a08 = next(r for r in results if r.check_code == "A08")
    assert a08.state == ValidationState.NOT_RUN
    assert a08.state is not ValidationState.PASS


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
