"""发布只接受本次固定输入的执行结果；失败不改变历史版本。"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.ontology_validation_context import working_context
from app.domain.status_service import publish_resource
from app.domain.template_service import create_template
from app.domain.type_service import create_entity_type
from app.domain.validation_service import run_ontology_validation
from app.models.domain import (
    Ontology,
    OntologyResourceRef,
    OntologyRevision,
    OntologyRuleRef,
)
from app.models.enums import ResourceKind, ResourceStatus, ValidationState
from app.models.governance import Rule
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    ObjectPropDetail,
    ResourceParent,
    ResourceRef,
)
from app.models.validation import ValidationReport
from app.schemas.ontology import OntologyCreate
from app.schemas.template import TemplateCreate, TemplateResource
from app.schemas.type import EntityTypeCreate
from app.schemas.validation import OntologyValidationTarget
from app.semantics.backend import SemanticBackend
from app.semantics.rdflib_backend import RdflibBackend
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/publication.db")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.mark.parametrize(
    "owned_child,explicit_child", [(False, False), (True, False), (True, True)]
)
def test_final_owned_pin_excludes_dependencies_of_provisional_version(
    session: Session,
    owned_child: bool,
    explicit_child: bool,
) -> None:
    ns = register_namespace(session, "residue", "https://example.org/residue/")
    onto = create_ontology(
        session,
        OntologyCreate(
            name="Residue", iri="urn:residue", label_i18n={"zh-CN": "依赖闭包"}
        ),
    )

    def resource(name: str, kind: ResourceKind) -> ModelResource:
        item = ModelResource(
            name=name,
            iri=ns.iri + name,
            namespace_id=ns.id,
            kind=kind,
            label_i18n={"zh-CN": name},
        )
        session.add(item)
        session.flush()
        return item

    old = resource("OldParent", ResourceKind.ENTITY)
    new = resource("NewParent", ResourceKind.ENTITY)
    assoc = resource("Association", ResourceKind.ASSOC)
    child = (
        resource("Association.value", ResourceKind.DATATYPE_PROP)
        if owned_child
        else None
    )
    owner = resource("ownedRelation", ResourceKind.OBJECT_PROP)
    root = resource("rootRelation", ResourceKind.OBJECT_PROP)
    session.add_all(
        [
            ResourceParent(child_id=assoc.id, parent_id=old.id),
            ResourceRef(source_id=owner.id, target_id=old.id, role="relation_domain"),
            ResourceRef(source_id=owner.id, target_id=assoc.id, role="relation_range"),
            ResourceRef(source_id=owner.id, target_id=assoc.id, role="assoc_resource"),
            ObjectPropDetail(resource_id=owner.id),
            ResourceRef(source_id=root.id, target_id=assoc.id, role="relation_domain"),
            ResourceRef(source_id=root.id, target_id=old.id, role="relation_range"),
            ResourceRef(source_id=root.id, target_id=owner.id, role="inverse_of"),
            ObjectPropDetail(resource_id=root.id),
        ]
    )
    if child is not None:
        session.add_all(
            [
                ResourceRef(source_id=assoc.id, target_id=child.id, role="data_prop"),
                DatatypePropDetail(
                    resource_id=child.id, prop_name="value", datatype="integer"
                ),
            ]
        )
        publish_resource(session, child)
    for item in (old, new, assoc, owner, root):
        publish_resource(session, item)
    session.execute(delete(ResourceParent).where(ResourceParent.child_id == assoc.id))
    session.add(ResourceParent(child_id=assoc.id, parent_id=new.id))
    assoc.status = ResourceStatus.DRAFT
    if child is not None:
        session.get(DatatypePropDetail, child.id).datatype = "string"
        child.status = ResourceStatus.DRAFT
    publish_resource(session, assoc)
    session.add(
        OntologyResourceRef(ontology_id=onto.id, resource_id=root.id, pinned_revision=1)
    )
    if explicit_child:
        assert child is not None
        session.add(
            OntologyResourceRef(
                ontology_id=onto.id, resource_id=child.id, pinned_revision=2
            )
        )
    session.flush()
    if explicit_child:
        with pytest.raises(KGError) as error:
            working_context(session, onto)
        assert error.value.code == ErrorCode.REVISION_CONFLICT
        return
    context = working_context(session, onto)
    assert context.resolved_versions[assoc.id] == 1
    assert context.payloads[assoc.id]["parent_ids"] == [old.id]
    assert new.id not in context.payloads
    assert new.id not in context.resolved_versions
    if child is not None:
        assert context.resolved_versions[child.id] == 1


def model(session: Session) -> tuple[Ontology, ModelResource]:
    ns = register_namespace(session, "ex", "https://example.org/publication/")
    entity = create_entity_type(
        session,
        EntityTypeCreate(
            name="Equipment",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "设备"},
        ),
    )
    publish_resource(session, entity)
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="EquipmentModel",
            iri="https://example.org/publication/model",
            label_i18n={"zh-CN": "设备模型"},
            ref_resource_ids=[entity.id],
        ),
    )
    session.commit()
    return ontology, entity


def test_unpublished_working_draft_executes_real_reasoner(session: Session) -> None:
    ontology, _ = model(session)
    report = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.WORKING,
        backend=RdflibBackend(),
    )
    assert report.binding is not None
    assert report.binding["working_draft_id"] == f"ontology:{ontology.id}:working"
    assert report.binding["edit_revision"] == ontology.edit_revision
    assert report.binding["target"] == "WORKING"
    assert (
        next(row.state for row in report.results if row.check_code == "A08")
        == ValidationState.PASS
    )
    assert ontology.current_revision == 0


def test_old_report_cannot_authorize_changed_resource(session: Session) -> None:
    ontology, entity = model(session)
    initial = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.WORKING,
        backend=RdflibBackend(),
    )
    original_digest = initial.binding["content_digest"]
    session.commit()
    entity.status = ResourceStatus.DRAFT
    entity.label_i18n = {"en-US": "Equipment"}
    publish_resource(session, entity)
    session.commit()
    before_edit = ontology.edit_revision
    with pytest.raises(KGError) as error, session.begin():
        publish_ontology(session, ontology, before_edit)
    assert error.value.code == ErrorCode.VALIDATION_VIOLATION
    session.refresh(ontology)
    assert ontology.current_revision == 0
    assert ontology.edit_revision == before_edit
    assert session.scalar(select(func.count()).select_from(OntologyRevision)) == 0
    current = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.WORKING,
        backend=RdflibBackend(),
    )
    assert current.binding["content_digest"] != original_digest
    assert (
        next(row.state for row in current.results if row.check_code == "A02")
        == ValidationState.VIOLATION
    )


def test_publish_rejects_required_not_run(session: Session) -> None:
    ontology, _ = model(session)
    backend = Mock(spec=SemanticBackend)
    backend.has_full_reasoner.return_value = False
    with pytest.raises(KGError) as error, session.begin():
        publish_ontology(session, ontology, backend=backend)
    assert {"check_code": "A08", "state": "NOT_RUN"} in error.value.params["checks"]
    session.refresh(ontology)
    assert ontology.current_revision == 0
    assert session.scalar(select(func.count()).select_from(ValidationReport)) == 0


def test_successful_publication_keeps_digest_and_independent_draft_target(
    session: Session,
) -> None:
    ontology, _ = model(session)
    publish_ontology(session, ontology)
    session.commit()
    frozen = session.scalar(select(OntologyRevision))
    assert frozen is not None
    evidence = frozen.metadata_snapshot["governance"]["validation"]
    report = session.get(ValidationReport, evidence["report_id"])
    assert report.binding["content_digest"] == evidence["content_digest"]
    old = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.PUBLISHED,
        backend=RdflibBackend(),
    )
    ontology.definition_i18n = {"zh-CN": "工作稿新定义"}
    ontology.edit_revision += 1
    session.flush()
    working = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.WORKING,
        backend=RdflibBackend(),
    )
    historical = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.PUBLISHED,
        backend=RdflibBackend(),
    )
    assert working.binding["content_digest"] != old.binding["content_digest"]
    assert historical.binding == old.binding
    assert frozen.metadata_snapshot["definition_i18n"] is None


def test_historical_validation_uses_frozen_rules_and_template(session: Session) -> None:
    ontology, entity = model(session)
    template = create_template(
        session,
        TemplateCreate(
            name="EquipmentTemplate",
            label_i18n={"zh-CN": "设备模板"},
            source="ENTERPRISE",
            basis="Project test",
            resources=[TemplateResource(resource_id=entity.id, pinned_revision=1)],
        ),
    )
    ontology.template_id = template.id
    rule = Rule(
        identifier="EquipmentAxiom",
        name_i18n={"zh-CN": "设备公理"},
        category="SEMANTIC",
        source_kind="ENTERPRISE",
        source_reference="test",
        target_iri=entity.iri,
        severity="VIOLATION",
        language="OWL",
        expression=f"<{entity.iri}> "
        f"<http://www.w3.org/2000/01/rdf-schema#subClassOf> <{entity.iri}> .",
        execution="AUTO",
        positive_example="",
        negative_example="",
        revision=1,
    )
    session.add(rule)
    session.flush()
    session.add(
        OntologyRuleRef(ontology_id=ontology.id, rule_id=rule.id, pinned_revision=1)
    )
    publish_ontology(session, ontology)
    session.commit()
    original = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.PUBLISHED,
        backend=RdflibBackend(),
    )
    binding = original.binding
    template.payload = {"resources": [{"resource_id": 999, "pinned_revision": 1}]}
    template.revision += 1
    rule.expression = "invalid changed content"
    rule.revision += 1
    session.flush()
    historical = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.PUBLISHED,
        backend=RdflibBackend(),
    )
    assert historical.binding == binding
    assert all(
        item.state == ValidationState.PASS
        for item in historical.results
        if item.check_code in {"A05", "A06", "A08"}
    )
    working = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.WORKING,
        backend=RdflibBackend(),
    )
    assert any(
        item.state == ValidationState.VIOLATION
        for item in working.results
        if item.check_code in {"A05", "A06"}
    )


def test_legacy_template_applicability_is_not_guessed_from_live_metadata(
    session: Session,
) -> None:
    ontology, _ = model(session)
    publish_ontology(session, ontology)
    session.commit()
    revision = session.scalar(select(OntologyRevision))
    revision.metadata_snapshot = {
        key: value
        for key, value in revision.metadata_snapshot.items()
        if key != "governance"
    }
    ontology.template_id = None
    session.flush()
    report = run_ontology_validation(
        session,
        ontology.id,
        target=OntologyValidationTarget.PUBLISHED,
        backend=RdflibBackend(),
    )
    assert (
        next(item.state for item in report.results if item.check_code == "A06")
        == ValidationState.NOT_RUN
    )
