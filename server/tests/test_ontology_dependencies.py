"""Top-level UI publication must freeze and export owned resources as well."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.db import Base
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.ontology_export_service import export_ontology
from app.domain.ontology_history_service import (
    get_revision_contents,
    get_revision_resource,
)
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.relation_service import create_relation_type, publish_relation_type
from app.domain.resource_lifecycle import unpublish_resource
from app.domain.status_service import get_revision, publish_resource
from app.domain.type_service import (
    create_entity_type,
    publish_entity_type,
    update_entity_type,
)
from app.models.domain import OntologyRevision
from app.models.enums import ResourceStatus
from app.models.resource import ModelResource, ResourceRef
from app.schemas.ontology import OntologyCreate
from app.schemas.relation import EndpointSpec, RelationTypeCreate
from app.schemas.type import DataTypePropCreate, EntityTypeCreate, EntityTypeUpdate
from rdflib import Graph
from rdflib.compare import isomorphic
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/closure.sqlite")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def test_ui_publication_freezes_owned_and_external_dependency_closure(
    session: Session,
) -> None:
    ns = register_namespace(session, "ex", "https://example.org/kg#")
    employee = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工"},
            data_props=[
                DataTypePropCreate(
                    name="Name", datatype="string", default_value="Original"
                )
            ],
        ),
    )
    publish_entity_type(session, employee)
    relation = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksWith",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "合作"},
            domain_spec=EndpointSpec(type_id=employee.id),
            range_spec=EndpointSpec(type_id=employee.id),
            enable_attributes=True,
            attribute_defs=[{"name": "Since", "datatype": "date"}],
        ),
    )
    publish_relation_type(session, relation)
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="Closure",
            iri="https://example.org/ontology/closure",
            label_i18n={"zh-CN": "闭包"},
            ref_resource_ids=[relation.id],
        ),
    )
    publish_ontology(session, ontology)
    session.commit()
    contents = get_revision_contents(session, ontology.id, 1)
    assert {item.name for item in contents.resources} == {
        "Employee",
        "Employee.Name",
        "WorksWith",
        "WorksWithAssociation",
        "WorksWithAssociation.Since",
    }
    before = Graph().parse(
        data=export_ontology(session, ontology.id).content, format="turtle"
    )
    name_id = next(
        item.resource_id for item in contents.resources if item.name == "Employee.Name"
    )
    assert get_revision_resource(session, ontology.id, 1, name_id).revision == 1
    unpublish_resource(session, employee)
    update_entity_type(
        session,
        employee,
        EntityTypeUpdate(
            if_match=1,
            edit_revision=employee.edit_revision,
            data_props=[
                DataTypePropCreate(
                    name="Name", datatype="string", default_value="Changed"
                )
            ],
        ),
    )
    publish_entity_type(session, employee)
    session.commit()
    assert get_revision_resource(session, ontology.id, 1, name_id).revision == 1
    after = Graph().parse(
        data=export_ontology(session, ontology.id).content, format="turtle"
    )
    assert isomorphic(before, after)
    root = get_revision_resource(session, ontology.id, 1, employee.id)
    assert root.snapshot.datatype_props[0].default_value == "Original"
    standalone = get_revision_resource(session, ontology.id, 1, name_id)
    assert standalone.snapshot.datatype_props[0].datatype == "string"
    assert standalone.snapshot.datatype_props[0].default_value == "Original"


def test_explicit_conflicting_child_pin_and_legacy_missing_pin_do_not_guess(
    session: Session,
) -> None:
    ns = register_namespace(session, "ex", "https://example.org/kg#")
    owner = create_entity_type(
        session,
        EntityTypeCreate(
            name="Owner",
            namespace_id=ns.id,
            label_i18n={},
            data_props=[DataTypePropCreate(name="Name", datatype="string")],
        ),
    )
    publish_entity_type(session, owner)
    child_id = session.scalar(
        select(ResourceRef.target_id).where(ResourceRef.source_id == owner.id)
    )
    child = session.get(ModelResource, child_id)
    assert child is not None
    child.status = ResourceStatus.DRAFT
    publish_resource(session, child)
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="Conflict",
            iri="https://example.org/conflict",
            label_i18n={},
            ref_resource_ids=[owner.id, child.id],
        ),
    )
    session.commit()
    with pytest.raises(KGError) as caught:
        publish_ontology(session, ontology)
    assert caught.value.code.value == "KG.REVISION_CONFLICT"
    session.rollback()
    assert session.scalar(select(OntologyRevision.id)) is None
    frozen = get_revision(session, owner.id, 1)
    frozen.payload = {k: v for k, v in frozen.payload.items() if k != "owned_versions"}
    legacy = create_ontology(
        session,
        OntologyCreate(
            name="Legacy",
            iri="https://example.org/legacy",
            label_i18n={},
            ref_resource_ids=[owner.id, child.id],
        ),
    )
    session.commit()
    with pytest.raises(KGError) as caught:
        publish_ontology(session, legacy)
    assert caught.value.params["reason"] == "missing_owned_version"
    session.rollback()
    assert session.scalar(select(OntologyRevision.id)) is None


def test_unchanged_shared_owned_property_keeps_one_frozen_revision(
    session: Session,
) -> None:
    ns = register_namespace(session, "ex", "https://example.org/kg#")
    first = create_entity_type(
        session,
        EntityTypeCreate(
            name="First",
            namespace_id=ns.id,
            label_i18n={},
            data_props=[DataTypePropCreate(name="Code", datatype="string")],
        ),
    )
    second = create_entity_type(
        session,
        EntityTypeCreate(
            name="Second",
            namespace_id=ns.id,
            label_i18n={},
        ),
    )
    child_id = session.scalar(
        select(ResourceRef.target_id).where(ResourceRef.source_id == first.id)
    )
    assert child_id is not None
    session.add(ResourceRef(source_id=second.id, target_id=child_id, role="data_prop"))
    session.flush()
    publish_entity_type(session, first)
    publish_entity_type(session, second)
    child = session.get(ModelResource, child_id)
    assert child is not None and child.current_revision == 1
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="Shared",
            iri="https://example.org/shared",
            label_i18n={},
            ref_resource_ids=[first.id, second.id],
        ),
    )
    publish_ontology(session, ontology)
    session.commit()
    assert {
        item.revision
        for item in get_revision_contents(session, ontology.id, 1).resources
    } == {1}
