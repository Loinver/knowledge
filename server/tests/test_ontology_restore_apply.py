"""PC09：两个独立数据库的语义往返、预览绑定及事务失败保护。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.errors import install_error_handler
from app.api.v1.ontology_restore import router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain import ontology_restore_service
from app.domain.enum_dictionary_service import create_dictionary, update_dictionary
from app.domain.iri_service import register_namespace
from app.domain.ontology_export_service import export_ontology
from app.domain.ontology_restore_service import inspect_restore, restore_ontology
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.relation_service import create_relation_type
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.models.domain import Ontology, OntologyRevision
from app.models.enum_dictionary import EnumDictionary
from app.models.enums import ResourceStatus
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    Namespace,
    ResourceRevision,
)
from app.schemas.enum_dictionary import EnumDictionaryInput
from app.schemas.ontology import OntologyCreate, OntologyExportFormat
from app.schemas.ontology_restore import OntologyRestoreRequest
from app.schemas.relation import CardinalitySpec, EndpointSpec, RelationTypeCreate
from app.schemas.type import DataTypePropCreate, EntityTypeCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import OWL, SH, BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.term import Node
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def destination(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/destination.sqlite")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: object, _record: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def source_content(tmp_path: Path, rdf_format: OntologyExportFormat) -> str:
    engine = create_engine(f"sqlite:///{tmp_path}/source.sqlite")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        namespace = register_namespace(db, "restore", "https://example.org/restore#")
        enum_input = EnumDictionaryInput(
            name="EmploymentStatus",
            label_i18n={"zh-CN": "状态", "en-US": "Status"},
            definition_i18n={"zh-CN": "合成字典", "en-US": "Synthetic dictionary"},
            entries=[
                {"value": "ACTIVE", "label_i18n": {"zh-CN": "在职", "en-US": "Active"}},
                {"value": "LEFT", "label_i18n": {"zh-CN": "离职", "en-US": "Left"}},
            ],
        )
        create_dictionary(db, enum_input.model_copy(update={"name": "UnrelatedEnum"}))
        dictionary = create_dictionary(db, enum_input)
        update_dictionary(db, dictionary.id, enum_input, 1)
        person = create_entity_type(
            db,
            EntityTypeCreate(
                name="Person", namespace_id=namespace.id, label_i18n={"zh-CN": "人"}
            ),
        )
        employee = create_entity_type(
            db,
            EntityTypeCreate(
                name="Employee",
                namespace_id=namespace.id,
                label_i18n={"zh-CN": "员工", "en-US": "Employee"},
                definition_i18n={"zh-CN": "合成员工定义"},
                parent_ids=[person.id],
                data_props=[
                    DataTypePropCreate(
                        name="Status",
                        datatype="enum",
                        enum_dict_id=dictionary.id,
                        enum_dict_revision=2,
                        default_value="ACTIVE",
                        nullable=False,
                        min_cardinality=1,
                        max_cardinality=1,
                        label_i18n={"zh-CN": "状态"},
                    ),
                    DataTypePropCreate(
                        name="Salary",
                        datatype="decimal",
                        min_value="0",
                        max_value="100.5",
                        min_cardinality=0,
                        max_cardinality=1,
                        default_value="10",
                        source_clause_ref="EXAMPLE 1",
                        label_i18n={"zh-CN": "薪水"},
                        definition_i18n={"zh-CN": "演示定义"},
                    ),
                ],
            ),
        )
        department = create_entity_type(
            db,
            EntityTypeCreate(
                name="Department",
                namespace_id=namespace.id,
                label_i18n={"zh-CN": "部门"},
            ),
        )
        relation = create_relation_type(
            db,
            RelationTypeCreate(
                name="WorksFor",
                namespace_id=namespace.id,
                label_i18n={"zh-CN": "任职"},
                domain_spec=EndpointSpec(
                    type_id=employee.id,
                    role_i18n={"zh-CN": "雇员"},
                    cardinality=CardinalitySpec(
                        min=0, max=2, role_label_i18n={"zh-CN": "任职数"}
                    ),
                ),
                range_spec=EndpointSpec(type_id=department.id),
                enable_attributes=True,
                attribute_defs=[
                    {
                        "name": "Note",
                        "datatype": "string",
                        "label_i18n": {"zh-CN": "备注"},
                    }
                ],
            ),
        )
        for resource in [person, employee, department, relation]:
            publish_resource(db, resource)
        ontology = create_ontology(
            db,
            OntologyCreate(
                name="RestoreOntology",
                iri="https://example.org/restore/ontology",
                label_i18n={"zh-CN": "恢复测试", "en-US": "Restore test"},
                definition_i18n={"zh-CN": "往返测试"},
                ref_resource_ids=[person.id, employee.id, department.id, relation.id],
            ),
        )
        publish_ontology(db, ontology)
        ontology.status = ResourceStatus.DRAFT
        publish_ontology(db, ontology, ontology.edit_revision)
        db.commit()
        content = export_ontology(db, ontology.id, rdf_format).content
    engine.dispose()
    return content


def normalized_graph(content: str, rdf_format: str) -> Graph:
    """Only local version/enum identities may differ; all semantics stay."""
    graph = Graph().parse(data=content, format=rdf_format)
    output = Graph()
    enum_predicate = URIRef("urn:knowledge:semantics:enumDictionary")
    enum_nodes = set(graph.objects(None, enum_predicate))
    replacements = {
        node: URIRef("urn:restored:enum:EmploymentStatus") for node in enum_nodes
    }
    for enum_node in enum_nodes:
        for entry in graph.objects(enum_node, URIRef("urn:knowledge:semantics:entry")):
            replacements[entry] = BNode()
    for shape in graph.objects(None, SH.property):
        if "relation-shape" in str(shape):
            replacements[shape] = BNode()

    def normalize(node: Node) -> Node:
        return replacements.get(node, node)

    for subject, predicate, value in graph:
        if predicate == OWL.versionInfo or (
            subject in enum_nodes
            and predicate == URIRef("urn:knowledge:semantics:revision")
        ):
            value = Literal("local-version")
        # Enum entry node IDs and relation shape names also contain local IDs.
        # Their connected triples, constraints and values remain in the comparison.
        output.add((normalize(subject), predicate, normalize(value)))
    return output


@pytest.mark.parametrize("rdf_format", list(OntologyExportFormat))
def test_export_restore_reexport_between_independent_databases(
    destination: Session, tmp_path: Path, rdf_format: OntologyExportFormat
) -> None:
    content = source_content(tmp_path, rdf_format)
    _, preview = inspect_restore(destination, rdf_format.value, content)
    assert preview.can_apply, preview.model_dump()
    result = restore_ontology(
        destination,
        OntologyRestoreRequest(
            format=rdf_format.value,
            content=content,
            preview_digest=preview.preview_digest,
        ),
    )
    destination.commit()
    assert result.current_revision == 1 and result.source_revision == 2
    assert result.created_resource_count == 8
    assert result.created_dictionary_count == 1
    assert destination.scalar(select(EnumDictionary)).revision == 1
    props = list(destination.scalars(select(DatatypePropDetail)))
    assert len(props) == 3
    enum_prop = next(prop for prop in props if prop.datatype == "enum")
    assert (enum_prop.enum_dict_id, enum_prop.enum_dict_revision) == (1, 1)
    assert all(
        rev.revision == 1 for rev in destination.scalars(select(ResourceRevision))
    )
    exported = export_ontology(destination, result.ontology_id, rdf_format).content
    before = normalized_graph(content, rdf_format.value)
    after = normalized_graph(exported, rdf_format.value)
    assert isomorphic(before, after), (
        set(before) - set(after),
        set(after) - set(before),
    )
    _, second = inspect_restore(destination, rdf_format.value, exported)
    assert not second.can_apply


def client_for(session: Session) -> TestClient:
    app = FastAPI()
    install_error_handler(app)
    app.include_router(router, prefix="/api/v1")
    sessions = sessionmaker(session.get_bind(), expire_on_commit=False)

    def request_session() -> Iterator[Session]:
        with sessions() as request:
            yield request

    app.dependency_overrides[get_session] = request_session
    return TestClient(app)


def test_apply_rechecks_digest_and_conflicts_before_writes(
    destination: Session, tmp_path: Path
) -> None:
    content = source_content(tmp_path, OntologyExportFormat.TURTLE)
    client = client_for(destination)
    payload = {"format": "turtle", "content": content}
    preview = client.post(
        "/api/v1/ontologies/import/restore-preview", json=payload
    ).json()
    assert preview["can_apply"]
    payload["preview_digest"] = preview["preview_digest"]
    tampered = client.post(
        "/api/v1/ontologies/import/restore", json={**payload, "content": content + "\n"}
    )
    assert tampered.status_code == 409
    assert destination.scalar(select(func.count()).select_from(Namespace)) == 0
    namespace = register_namespace(
        destination, "restore", "https://example.org/changed#"
    )
    destination.commit()
    stale = client.post("/api/v1/ontologies/import/restore", json=payload)
    assert stale.status_code == 409
    assert destination.scalar(select(func.count()).select_from(Ontology)) == 0
    assert namespace.iri == "https://example.org/changed#"


def test_failure_after_resource_creation_rolls_back_every_new_row(
    destination: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = source_content(tmp_path, OntologyExportFormat.TURTLE)
    client = client_for(destination)
    payload = {"format": "turtle", "content": content}
    preview = client.post(
        "/api/v1/ontologies/import/restore-preview", json=payload
    ).json()

    def fail_after_writes(session: Session, _ontology: Ontology) -> int:
        assert session.scalar(select(func.count()).select_from(ResourceRevision)) > 0
        raise KGError(ErrorCode.VALIDATION_VIOLATION, {"reason": "injected_failure"})

    monkeypatch.setattr(ontology_restore_service, "publish_ontology", fail_after_writes)
    response = client.post(
        "/api/v1/ontologies/import/restore",
        json={**payload, "preview_digest": preview["preview_digest"]},
    )
    assert response.status_code == 422
    for model in (
        Namespace,
        EnumDictionary,
        ModelResource,
        ResourceRevision,
        Ontology,
        OntologyRevision,
    ):
        assert destination.scalar(select(func.count()).select_from(model)) == 0


def test_unsupported_semantics_cannot_be_applied(
    destination: Session, tmp_path: Path
) -> None:
    content = source_content(tmp_path, OntologyExportFormat.TURTLE)
    content += (
        "\n<https://example.org/restore/ontology> "
        '<urn:knowledge:semantics:ruleSnapshot> "opaque" .'
    )
    client = client_for(destination)
    payload = {"format": "turtle", "content": content}
    preview = client.post(
        "/api/v1/ontologies/import/restore-preview", json=payload
    ).json()
    assert not preview["can_apply"] and preview["unsupported_triples"]
    response = client.post(
        "/api/v1/ontologies/import/restore",
        json={**payload, "preview_digest": preview["preview_digest"]},
    )
    assert response.status_code == 422
    assert destination.scalar(select(func.count()).select_from(ModelResource)) == 0


@pytest.mark.parametrize("rdf_format", list(OntologyExportFormat))
@pytest.mark.parametrize("role", ["union_of", "intersection_of"])
def test_unexportable_reference_roles_are_reported_and_rejected_before_restore(
    destination: Session,
    tmp_path: Path,
    rdf_format: OntologyExportFormat,
    role: str,
) -> None:
    source = source_content(tmp_path, rdf_format)
    graph = Graph().parse(data=source, format=rdf_format.value)
    graph.add(
        (
            URIRef("https://example.org/restore#WorksFor"),
            URIRef(f"urn:knowledge:ref:{role}"),
            URIRef("https://example.org/restore#WorksFor"),
        )
    )
    content = graph.serialize(format=rdf_format.value)
    client = client_for(destination)
    payload = {"format": rdf_format.value, "content": content}
    preview = client.post(
        "/api/v1/ontologies/import/restore-preview", json=payload
    ).json()
    assert not preview["can_apply"]
    assert any(f"urn:knowledge:ref:{role}" in t for t in preview["unsupported_triples"])
    response = client.post(
        "/api/v1/ontologies/import/restore",
        json={**payload, "preview_digest": preview["preview_digest"]},
    )
    assert response.status_code == 422
    for model in (Ontology, ModelResource, ResourceRevision, Namespace, EnumDictionary):
        assert destination.scalar(select(func.count()).select_from(model)) == 0
