"""本体装配与设计器集成测试（H-13）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import (
    add_ref,
    create_ontology,
    detect_conflicts,
    get_canvas_layout,
    list_refs,
    publish_ontology,
    remove_ref,
    update_canvas_layout,
    update_ontology,
)
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.models.enums import ResourceStatus
from app.schemas.ontology import (
    OntologyCreate,
    OntologyRefAdd,
    OntologyUpdate,
)
from app.schemas.type import EntityTypeCreate
from sqlalchemy import create_engine
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


def _make_ontology(session, name="HR-Ontology", ref_ids=None):
    return create_ontology(
        session,
        OntologyCreate(
            name=name,
            iri=f"https://example.org/onto#{name}",
            label_i18n={"zh-CN": "人力资本", "en-US": "Human Capital"},
            ref_resource_ids=ref_ids or [],
        ),
    )


def test_create_ontology(session):
    onto = _make_ontology(session)
    session.commit()
    assert onto.name == "HR-Ontology"
    assert onto.status == ResourceStatus.DRAFT
    assert onto.current_revision == 0


def test_create_duplicate_rejected(session):
    _make_ontology(session)
    with pytest.raises(KGError) as exc:
        _make_ontology(session)
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_add_ref_deduped_by_resource(session, published_type):
    onto = _make_ontology(session)
    ref = add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    with pytest.raises(KGError) as exc:
        add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED
    assert ref.resource_id == published_type.id


def test_add_nonexistent_ref_rejected(session):
    onto = _make_ontology(session)
    with pytest.raises(KGError) as exc:
        add_ref(session, onto.id, OntologyRefAdd(resource_id=9999))
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_publish_freezes_resource_versions(session, published_type):
    onto = _make_ontology(session, ref_ids=[published_type.id])
    rev = publish_ontology(session, onto)
    session.commit()
    assert rev == 1
    assert onto.status == ResourceStatus.PUBLISHED
    revisions = list_refs(session, onto.id)
    assert len(revisions) == 1
    assert onto.current_revision == 1
    from app.models.domain import OntologyRevision

    snapshot = (
        session.query(OntologyRevision).filter_by(ontology_id=onto.id, revision=1).one()
    )
    assert snapshot.resource_versions == {str(published_type.id): 1}


def test_publish_blocks_unpublished_member(session, ns):
    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工", "en-US": "Employee"},
        ),
    )
    onto = _make_ontology(session, ref_ids=[res.id])
    with pytest.raises(KGError) as exc:
        publish_ontology(session, onto)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_canvas_layout_no_semantic_version(session):
    onto = _make_ontology(session)
    session.commit()
    layout = update_canvas_layout(
        session, "ontology_designer", onto.id, {"node-1": {"x": 10, "y": 20}}
    )
    session.commit()
    assert layout.positions["node-1"]["x"] == 10
    assert onto.current_revision == 0
    fetched = get_canvas_layout(session, "ontology_designer", onto.id)
    assert fetched.positions == {"node-1": {"x": 10, "y": 20}}


def test_update_requires_if_match(session):
    onto = _make_ontology(session)
    session.commit()
    updated = update_ontology(
        session,
        onto,
        OntologyUpdate(
            label_i18n={"zh-CN": "新名", "en-US": "New"},
            if_match=0,
        ),
    )
    assert updated.label_i18n["zh-CN"] == "新名"
    with pytest.raises(KGError) as exc:
        update_ontology(
            session,
            onto,
            OntologyUpdate(label_i18n={"zh-CN": "x"}, if_match=99),
        )
    assert exc.value.code == ErrorCode.REVISION_CONFLICT


def test_remove_ref(session, published_type):
    onto = _make_ontology(session)
    ref = add_ref(session, onto.id, OntologyRefAdd(resource_id=published_type.id))
    session.commit()
    remove_ref(session, onto.id, ref.id)
    session.commit()
    assert list_refs(session, onto.id) == []


def test_detect_conflicts_empty_without_duplicates(session, published_type):
    onto = _make_ontology(session, ref_ids=[published_type.id])
    assert detect_conflicts(session, onto.id) == []
