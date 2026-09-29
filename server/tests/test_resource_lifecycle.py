"""资源生命周期扩展：撤回发布与草稿删除（实体类型/关系/本体/业务域）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.domain_service import add_member, create_domain, delete_domain
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import add_ref, create_ontology, delete_ontology
from app.domain.relation_service import create_relation_type
from app.domain.resource_lifecycle import delete_resource, unpublish_resource
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type, update_entity_type
from app.models.domain import BusinessDomain, Ontology
from app.models.enums import ResourceStatus
from app.models.governance import Rule
from app.models.resource import ModelResource
from app.schemas.domain import DomainCreate, DomainMemberAdd
from app.schemas.ontology import OntologyCreate, OntologyRefAdd
from app.schemas.relation import (
    CardinalitySpec,
    EndpointSpec,
    OwlFeatures,
    RelationTypeCreate,
)
from app.schemas.type import EntityTypeCreate, EntityTypeUpdate
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


def _make_domain(session, name):
    return create_domain(
        session,
        DomainCreate(
            name=name,
            iri=f"https://example.org/dom#{name}",
            label_i18n={"zh-CN": name, "en-US": name},
        ),
    )


def _make_type(session, ns, name="Employee"):
    return create_entity_type(
        session,
        EntityTypeCreate(
            name=name,
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工", "en-US": name},
        ),
    )


def _make_relation(session, ns, domain_type, range_type, name="WorksIn"):
    return create_relation_type(
        session,
        RelationTypeCreate(
            name=name,
            namespace_id=ns.id,
            label_i18n={"zh-CN": "任职", "en-US": name},
            domain_spec=EndpointSpec(
                type_id=domain_type.id, cardinality=CardinalitySpec(min=0, max=1)
            ),
            range_spec=EndpointSpec(
                type_id=range_type.id, cardinality=CardinalitySpec(min=0, max=-1)
            ),
            owl=OwlFeatures(),
        ),
    )


# ── 撤回发布 ────────────────────────────────────────────────────────────


def test_unpublish_allows_edit_and_republish(session, ns):
    res = _make_type(session, ns)
    publish_resource(session, res)
    session.commit()
    assert res.status == ResourceStatus.PUBLISHED

    unpublish_resource(session, res)
    session.commit()
    assert res.status == ResourceStatus.DRAFT
    assert res.current_revision == 1  # 历史版本保留

    updated = update_entity_type(
        session,
        res,
        EntityTypeUpdate(
            label_i18n={"zh-CN": "改过"},
            if_match=1,
            edit_revision=res.edit_revision,
        ),
    )
    assert updated.status == ResourceStatus.DRAFT
    publish_resource(session, updated)
    session.commit()
    assert updated.current_revision == 2


def test_unpublish_draft_rejected(session, ns):
    res = _make_type(session, ns)
    with pytest.raises(KGError) as exc:
        unpublish_resource(session, res)
    assert exc.value.code == ErrorCode.INVALID_REQUEST


# ── 草稿删除 ────────────────────────────────────────────────────────────


def test_delete_fresh_draft_relation(session, ns):
    employee = _make_type(session, ns, "Employee")
    department = _make_type(session, ns, "Department")
    relation = _make_relation(session, ns, employee, department)
    session.commit()

    delete_resource(session, relation)
    session.commit()
    assert session.get(ModelResource, relation.id) is None
    # 端点实体类型不受影响
    assert session.get(ModelResource, employee.id) is not None
    assert session.get(ModelResource, department.id) is not None


def test_delete_published_history_rejected(session, ns):
    res = _make_type(session, ns)
    publish_resource(session, res)
    session.commit()
    unpublish_resource(session, res)
    session.commit()
    # 撤回过发布就有版本历史，证据/快照可能按 id 钉住，不允许物理删除
    with pytest.raises(KGError) as exc:
        delete_resource(session, res)
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_delete_domain_member_rejected(session, ns):
    res = _make_type(session, ns)
    domain = _make_domain(session, "HR")
    add_member(session, domain.id, DomainMemberAdd(resource_id=res.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        delete_resource(session, res)
    assert exc.value.code == ErrorCode.RESOURCE_IN_USE


def test_delete_ontology_referenced_rejected(session, ns):
    res = _make_type(session, ns)
    onto = create_ontology(
        session,
        OntologyCreate(
            name="Core",
            iri="https://example.org/ont#Core",
            label_i18n={"zh-CN": "核心", "en-US": "Core"},
        ),
    )
    add_ref(session, onto.id, OntologyRefAdd(resource_id=res.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        delete_resource(session, res)
    assert exc.value.code == ErrorCode.RESOURCE_IN_USE


def test_delete_rule_targeted_rejected(session, ns):
    res = _make_type(session, ns)
    session.add(
        Rule(
            identifier="STD-ENTITY-001",
            name_i18n={"zh-CN": "实体命名", "en-US": "Entity naming"},
            category="core",
            source_kind="STANDARD",
            source_reference="GB/T 48000.3-2026#5.1",
            target_iri=res.iri,
            severity="VIOLATION",
            language="SHACL",
            expression="@prefix sh: <http://www.w3.org/ns/shacl#> .",
            execution="AUTO",
            positive_example="@prefix ex: <https://example.org/> .",
            negative_example="@prefix ex: <https://example.org/> .",
            revision=1,
        )
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        delete_resource(session, res)
    assert exc.value.code == ErrorCode.RESOURCE_IN_USE


def test_delete_endpoint_of_relation_rejected(session, ns):
    employee = _make_type(session, ns, "Employee")
    department = _make_type(session, ns, "Department")
    _make_relation(session, ns, employee, department)
    session.commit()
    with pytest.raises(KGError) as exc:
        delete_resource(session, employee)
    assert exc.value.code == ErrorCode.RESOURCE_IN_USE


def test_delete_parent_of_children_rejected_then_allowed(session, ns):
    parent = _make_type(session, ns, "Person")
    child = _make_type(session, ns, "Employee")
    update_entity_type(
        session, child, EntityTypeUpdate(parent_ids=[parent.id], if_match=0)
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        delete_resource(session, parent)
    assert exc.value.code == ErrorCode.RESOURCE_IN_USE

    # 先删子资源，父资源随之可删
    delete_resource(session, child)
    session.commit()
    delete_resource(session, parent)
    session.commit()
    assert session.get(ModelResource, parent.id) is None


# ── 本体 / 业务域删除 ───────────────────────────────────────────────────


def test_delete_ontology_cleanup(session, ns):
    res = _make_type(session, ns)
    onto = create_ontology(
        session,
        OntologyCreate(
            name="Core",
            iri="https://example.org/ont#Core",
            label_i18n={"zh-CN": "核心", "en-US": "Core"},
        ),
    )
    add_ref(session, onto.id, OntologyRefAdd(resource_id=res.id))
    session.commit()
    delete_ontology(session, onto.id)
    session.commit()
    assert session.get(ModelResource, res.id) is not None  # 资源本身不动
    assert session.scalar(select(func.count()).select_from(Ontology)) == 0


def test_delete_domain_leaf_and_children_guard(session, ns):
    parent = _make_domain(session, "HR")
    child = create_domain(
        session,
        DomainCreate(
            name="Payroll",
            iri="https://example.org/dom#Payroll",
            label_i18n={"zh-CN": "薪资", "en-US": "Payroll"},
            parent_id=parent.id,
        ),
    )
    with pytest.raises(KGError) as exc:
        delete_domain(session, parent.id)
    assert exc.value.code == ErrorCode.RESOURCE_IN_USE

    delete_domain(session, child.id)
    session.commit()
    delete_domain(session, parent.id)
    session.commit()
    assert session.scalar(select(func.count()).select_from(BusinessDomain)) == 0
