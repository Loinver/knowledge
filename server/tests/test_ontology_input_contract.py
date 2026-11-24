"""G06/G11/G13：写入输入契约与拒绝后的数据保护（仅临时 SQLite）。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.errors import install_error_handler
from app.api.v1.relations import router as relation_router
from app.api.v1.types import router as type_router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.ontology_export_service import export_ontology
from app.domain.ontology_import_service import apply_import, preview_import
from app.domain.ontology_restore_service import inspect_restore, restore_ontology
from app.domain.ontology_service import (
    create_ontology,
    publish_ontology,
    update_ontology,
)
from app.domain.ontology_snapshot import load_resource_snapshot
from app.domain.ontology_validation_context import working_context
from app.domain.relation_service import (
    create_relation_type,
    get_relation_meta,
    update_relation_type,
    validate_owl_compatibility,
)
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type, get_data_props, set_data_props
from app.iri import (
    build_iri,
    build_property_iri,
    is_valid_any_uri,
    is_valid_property_name,
)
from app.models.resource import DatatypePropDetail, ModelResource
from app.schemas.ontology import OntologyCreate, OntologyExportFormat, OntologyUpdate
from app.schemas.ontology_import import OntologyImportApplyRequest
from app.schemas.ontology_restore import OntologyRestoreRequest
from app.schemas.relation import (
    CardinalitySpec,
    OwlFeatures,
    RelationTypeCreate,
    RelationTypeUpdate,
)
from app.schemas.type import (
    DataTypePropCreate,
    EntityTypeCreate,
    EntityTypeUpdate,
    Synonym,
)
from app.semantics.ontology_rdf import (
    OntologyRdfMetadata,
    OntologyRdfResource,
    serialize_ontology_rdf,
)
from app.semantics.ontology_restore import parse_restore_document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pyshacl import validate
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS, XSD
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/input-contract.db")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as active:
            yield active
    finally:
        engine.dispose()


def test_legacy_import_rejects_unapplied_root_synonyms(
    session: Session, entity: ModelResource
) -> None:
    root = URIRef("https://example.org/People")
    graph = Graph()
    graph.add((root, RDF.type, OWL.Ontology))
    graph.add((root, SKOS.altLabel, Literal("People records", lang="en-US")))
    graph.add((URIRef(entity.iri), RDF.type, OWL.Class))
    graph.add((URIRef(entity.iri), RDFS.isDefinedBy, root))
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="People",
            iri=str(root),
            label_i18n={"zh-CN": "人员本体"},
        ),
    )
    session.commit()
    content = graph.serialize(format="turtle")
    preview = preview_import(session, "turtle", content, ontology.id)
    assert preview.synonyms is not None
    assert preview.synonyms[0].text == "People records"
    with pytest.raises(KGError) as error:
        apply_import(
            session,
            OntologyImportApplyRequest(
                format="turtle",
                content=content,
                ontology_id=ontology.id,
            ),
            revision=0,
            if_edit_match=0,
        )
    assert error.value.params["reason"] == "ontology_metadata_requires_restore"
    session.rollback()
    assert ontology.synonyms == []
    assert ontology.edit_revision == 0


def test_legacy_import_requires_explicit_alias_conflict_resolution(
    session: Session, entity: ModelResource
) -> None:
    subject = URIRef(entity.iri)
    graph = Graph()
    graph.add((subject, RDF.type, OWL.Class))
    graph.add((subject, SKOS.altLabel, Literal("Human", lang="en-US")))
    preview = preview_import(session, "turtle", graph.serialize(format="turtle"))
    assert preview.requires_resolution
    assert preview.resources[0].synonyms_present
    assert any(conflict.code == "SYNONYMS_MISMATCH" for conflict in preview.conflicts)


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app = FastAPI()
    install_error_handler(app)
    app.include_router(type_router)
    app.include_router(relation_router)

    def isolated_session() -> Iterator[Session]:
        with Session(session.get_bind(), expire_on_commit=False) as request_session:
            yield request_session

    app.dependency_overrides[get_session] = isolated_session
    with TestClient(app) as active:
        yield active


@pytest.fixture()
def entity(session: Session) -> ModelResource:
    ns = register_namespace(session, "kg", "https://example.org/kg#")
    resource = create_entity_type(
        session,
        EntityTypeCreate(
            name="Person", namespace_id=ns.id, label_i18n={"en-US": "Person"}
        ),
    )
    session.commit()
    return resource


def relation_payload(entity: ModelResource, **values: object) -> dict[str, object]:
    return {
        "name": "hasPeer",
        "namespace_id": entity.namespace_id,
        "label_i18n": {"en-US": "peer"},
        "domain_spec": {"type_id": entity.id},
        "range_spec": {"type_id": entity.id},
        **values,
    }


@pytest.mark.parametrize(
    "values",
    [
        {"name": ""},
        {"name": "bad/name"},
        {"name": "bad#name"},
        {"name": "bad.name"},
        {"name": "bad-name"},
        {"name": "name\n"},
        {"name": " name"},
        {"name": "1name"},
        {"name": "属性"},
        {"datatype": "unknown"},
        {"datatype": "float"},
        {"datatype": "STRING"},
        {"min_cardinality": -1},
        {"max_cardinality": -1},
        {"min_cardinality": 2, "max_cardinality": 1},
        {"nullable": False, "max_cardinality": 0},
        {"min_cardinality": True},
        {"max_cardinality": 1.5},
        {"max_cardinality": "2"},
        {"datatype": "string", "min_value": "0"},
        {"datatype": "date", "max_value": "2026-01-01"},
        {"datatype": "integer", "min_value": "0.5"},
        {"datatype": "decimal", "min_value": "NaN"},
        {"datatype": "decimal", "max_value": "Infinity"},
        {"datatype": "decimal", "min_value": "-Infinity"},
        {"datatype": "decimal", "min_value": ""},
        {"datatype": "decimal", "min_value": " 1"},
        {"datatype": "decimal", "min_value": "1_000"},
        {"datatype": "decimal", "min_value": "1e999999999"},
        {"datatype": "decimal", "min_value": "10", "max_value": "2"},
    ],
)
def test_invalid_data_property_rejected_over_http_without_writes(
    session: Session,
    client: TestClient,
    entity: ModelResource,
    values: dict[str, object],
) -> None:
    before = session.scalar(select(func.count()).select_from(ModelResource))
    response = client.post(
        "/entity-types",
        json={
            "name": "Document",
            "namespace_id": entity.namespace_id,
            "label_i18n": {"en-US": "Document"},
            "data_props": [{"name": "size", "datatype": "integer", **values}],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "KG.INVALID_REQUEST"
    assert response.json()["data"] is None
    assert session.scalar(select(func.count()).select_from(ModelResource)) == before


@pytest.mark.parametrize("name", ["hasPart", "HasPart", "ICS", "x1"])
def test_property_names_preserve_case_without_relaxing_class_names(name: str) -> None:
    assert is_valid_property_name(name)
    assert build_property_iri("https://example.org/kg#", name).endswith(f"#{name}")
    if name[0].islower():
        with pytest.raises(ValueError):
            build_iri("https://example.org/kg#", name)


def test_legacy_data_property_name_is_safe_without_relaxing_object_or_class_names() -> (
    None
):
    prop = DataTypePropCreate(name="credit_code", datatype="string")
    assert prop.name == "credit_code"
    assert not is_valid_property_name(prop.name)
    assert is_valid_property_name(prop.name, allow_legacy_underscore=True)
    with pytest.raises(ValueError):
        build_iri("https://example.org/kg#", prop.name)


@pytest.mark.parametrize(
    "datatype", ["string", "integer", "decimal", "boolean", "date", "anyURI"]
)
def test_supported_data_property_types(datatype: str) -> None:
    assert DataTypePropCreate(name="value", datatype=datatype).datatype == datatype


@pytest.mark.parametrize(
    "values",
    [
        {"datatype": "integer", "min_value": "-10", "max_value": "+10"},
        {"datatype": "decimal", "min_value": "-.5", "max_value": "0.50"},
        {"datatype": "decimal", "min_value": "0.1", "max_value": "0.1"},
        {"datatype": "integer", "min_cardinality": 0, "max_cardinality": 0},
    ],
)
def test_valid_data_property_bounds_roundtrip_with_stable_iri(
    session: Session,
    client: TestClient,
    entity: ModelResource,
    values: dict[str, object],
) -> None:
    payload = {"name": "Size", "datatype": "integer", **values}
    response = client.put(
        f"/entity-types/{entity.id}", json={"if_match": 0, "data_props": [payload]}
    )
    assert response.status_code == 200
    prop = response.json()["data_props"][0]
    assert prop["iri"] == f"{entity.iri}/Size"
    for key, value in payload.items():
        assert prop[key] == value
    second = client.put(
        f"/entity-types/{entity.id}",
        json={
            "if_match": response.json()["current_revision"],
            "edit_revision": response.json()["edit_revision"],
            "data_props": [payload],
        },
    )
    assert second.status_code == 200
    assert second.json()["data_props"][0]["iri"] == prop["iri"]


def test_internal_invalid_property_does_not_replace_existing_properties(
    session: Session, entity: ModelResource
) -> None:
    set_data_props(
        session, entity, [DataTypePropCreate(name="age", datatype="integer")]
    )
    session.commit()
    existing = get_data_props(session, entity)[0]
    invalid = DataTypePropCreate.model_construct(name="broken/name", datatype="unknown")
    with pytest.raises(KGError) as error:
        set_data_props(session, entity, [invalid])
    assert error.value.code == ErrorCode.INVALID_REQUEST
    session.commit()  # 校验在清旧集合之前；即使调用方捕获异常也不会半替换。
    assert get_data_props(session, entity)[0].id == existing.id
    assert session.get(DatatypePropDetail, existing.id).datatype == "integer"


@pytest.mark.parametrize("field,limit", [("name", 128), ("iri", 640)])
def test_property_identifier_budget_rejects_before_replacing_existing_properties(
    session: Session, entity: ModelResource, field: str, limit: int
) -> None:
    if field == "iri":
        # 长 IRI 夹具本身仍在列预算内，用于独立覆盖 IRI 超限分支。
        prefix = "https://example.org/"
        entity.iri = prefix + "a" * (limit - 33 - len(prefix))
    owner_name, owner_iri = entity.name, entity.iri
    local_length = limit - len(getattr(entity, field)) - 1
    boundary_name = "p" * local_length
    set_data_props(
        session, entity, [DataTypePropCreate(name=boundary_name, datatype="string")]
    )
    session.commit()
    existing = get_data_props(session, entity)[0]
    expected_name = f"{owner_name}.{boundary_name}"
    expected_iri = f"{owner_iri}/{boundary_name}"
    assert len(getattr(existing, field)) == limit
    before_count = session.scalar(select(func.count()).select_from(ModelResource))

    overflow_name = boundary_name + "p"
    assert len(overflow_name) <= 128  # local name 合法，只有合成标识超限。
    with pytest.raises(KGError) as error:
        set_data_props(
            session,
            entity,
            [
                DataTypePropCreate(name="new", datatype="string"),
                DataTypePropCreate(name=overflow_name, datatype="string"),
            ],
        )
    assert error.value.code == ErrorCode.INVALID_REQUEST
    assert error.value.params == {
        "reason": "property_identifier_too_long",
        "field": field,
        "property": overflow_name,
        "length": limit + 1,
        "max_length": limit,
    }
    session.commit()  # 即使调用方捕获后提交，也不能半替换旧集合。
    assert (
        session.scalar(select(func.count()).select_from(ModelResource)) == before_count
    )
    remaining = get_data_props(session, entity)
    assert [prop.id for prop in remaining] == [existing.id]
    assert (remaining[0].name, remaining[0].iri) == (expected_name, expected_iri)
    assert (entity.name, entity.iri) == (owner_name, owner_iri)
    detail = session.get(DatatypePropDetail, existing.id)
    assert detail is not None and detail.datatype == "string"


def test_duplicate_property_update_rolls_back_existing_collection(
    session: Session, client: TestClient, entity: ModelResource
) -> None:
    original = {"name": "age", "datatype": "integer"}
    assert (
        client.put(
            f"/entity-types/{entity.id}", json={"if_match": 0, "data_props": [original]}
        ).status_code
        == 200
    )
    before = client.get(f"/entity-types/{entity.id}").json()
    response = client.put(
        f"/entity-types/{entity.id}",
        json={
            "if_match": before["current_revision"],
            "edit_revision": before["edit_revision"],
            "label_i18n": {"en-US": "Changed"},
            "data_props": [original, original],
        },
    )
    assert response.status_code == 400
    assert client.get(f"/entity-types/{entity.id}").json() == before


@pytest.mark.parametrize("field", ["union_of", "intersection_of"])
def test_unsupported_relation_construct_create_and_update_do_not_write(
    session: Session, client: TestClient, entity: ModelResource, field: str
) -> None:
    response = client.post(
        "/relations", json=relation_payload(entity, **{field: [entity.id]})
    )
    assert response.status_code == 400
    assert response.json()["params"] == {
        "reason": "unsupported_relation_construct",
        "fields": [field],
    }
    assert session.scalar(select(func.count()).select_from(ModelResource)) == 1
    created = client.post("/relations", json=relation_payload(entity)).json()
    response = client.put(
        f"/relations/{created['id']}",
        json={"if_match": 0, field: [entity.id], "label_i18n": {"en-US": "changed"}},
    )
    assert response.status_code == 400
    assert client.get(f"/relations/{created['id']}").json() == created


@pytest.mark.parametrize("enabled", [False, True])
def test_association_mode_conversion_rejected_but_same_mode_is_accepted(
    client: TestClient, entity: ModelResource, enabled: bool
) -> None:
    created = client.post(
        "/relations", json=relation_payload(entity, enable_attributes=enabled)
    ).json()
    relation_id = created["id"]
    assert created["iri"] == "https://example.org/kg#hasPeer"
    if enabled:
        assert created["assoc_resource_id"] is not None
    response = client.put(
        f"/relations/{relation_id}",
        json={
            "if_match": 0,
            "enable_attributes": not enabled,
            "label_i18n": {"en-US": "changed"},
        },
    )
    assert response.status_code == 400
    assert (
        response.json()["params"]["reason"] == "association_mode_conversion_unsupported"
    )
    assert client.get(f"/relations/{relation_id}").json() == created
    assert (
        client.put(
            f"/relations/{relation_id}",
            json={
                "if_match": 0,
                "enable_attributes": enabled,
                "union_of": [],
                "intersection_of": [],
            },
        ).status_code
        == 200
    )


def test_invalid_association_property_rejected_without_orphan_resource(
    session: Session, client: TestClient, entity: ModelResource
) -> None:
    response = client.post(
        "/relations",
        json=relation_payload(
            entity,
            enable_attributes=True,
            attribute_defs=[{"name": "bad/name", "datatype": "anyURI"}],
        ),
    )
    assert response.status_code == 400
    assert response.json()["params"]["reason"] == "invalid_attribute_definition"
    assert session.scalar(select(func.count()).select_from(ModelResource)) == 1


@pytest.mark.parametrize("functional", ["functional", "inverse_functional"])
def test_symmetric_functional_features_persist_on_create_and_update(
    session: Session, entity: ModelResource, functional: str
) -> None:
    owl = OwlFeatures.model_validate({"symmetric": True, functional: True})
    relation = create_relation_type(
        session, RelationTypeCreate.model_validate(relation_payload(entity, owl=owl))
    )
    session.commit()
    assert get_relation_meta(session, relation)["owl"] == owl.model_dump()
    update_relation_type(session, relation, RelationTypeUpdate(if_match=0, owl=owl))
    session.commit()
    assert get_relation_meta(session, relation)["owl"] == owl.model_dump()


@pytest.mark.parametrize("feature", ["functional", "inverse_functional"])
def test_transitive_combinations_remain_explicit_product_restrictions(
    feature: str,
) -> None:
    with pytest.raises(KGError) as error:
        validate_owl_compatibility(
            OwlFeatures.model_validate({"transitive": True, feature: True})
        )
    assert error.value.params["reason"] == "unsupported_owl_feature_combination"


@pytest.mark.parametrize("values", [{"min": True}, {"max": 0.5}, {"min": 2, "max": 1}])
def test_relation_cardinality_rejects_invalid_inputs(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CardinalitySpec.model_validate(values)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://example.org/a%20b",
        "urn:example:item:1",
        "relative/path",
        "https://example.org/文档",
    ],
)
def test_any_uri_defaults_preserve_valid_uri_references(value: str) -> None:
    assert is_valid_any_uri(value)
    assert (
        DataTypePropCreate(
            name="link", datatype="anyURI", default_value=value
        ).default_value
        == value
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://example.org/a b",
        "https://example.org/%ZZ",
        "https://[broken",
        "line\nfeed",
        "https://example.org/<x>",
    ],
)
def test_any_uri_defaults_reject_invalid_lexical_values(value: str) -> None:
    assert not is_valid_any_uri(value)
    with pytest.raises(ValidationError):
        DataTypePropCreate(name="link", datatype="anyURI", default_value=value)


@pytest.mark.parametrize(
    "model", [EntityTypeUpdate, RelationTypeUpdate, OntologyUpdate]
)
@pytest.mark.parametrize(
    "values",
    [
        None,
        ["Device"],
        [{"language": "de", "text": "Device"}],
        [{"language": "en-US", "text": " "}],
        [{"language": "en-US", "text": "Device", "extra": "ignored"}],
        [{"language": "en-US", "text": "Device"}] * 2,
    ],
)
def test_synonyms_reject_invalid_and_duplicate_input(
    model: type, values: object
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({"if_match": 0, "synonyms": values})
    assert model.model_validate({"if_match": 0}).synonyms is None
    assert model.model_validate({"if_match": 0, "synonyms": []}).synonyms == []


def test_synonyms_entity_and_property_update_preserve_omitted_fields(
    client: TestClient,
    entity: ModelResource,
) -> None:
    aliases = [
        {"language": "en-US", "text": "Human"},
        {"language": "zh-CN", "text": "人员"},
    ]
    response = client.put(
        f"/entity-types/{entity.id}",
        json={
            "if_match": 0,
            "synonyms": aliases,
            "data_props": [{"name": "link", "datatype": "anyURI", "synonyms": aliases}],
        },
    )
    assert response.status_code == 200
    first = response.json()
    assert first["synonyms"] == first["data_props"][0]["synonyms"] == aliases
    response = client.put(
        f"/entity-types/{entity.id}",
        json={
            "if_match": first["current_revision"],
            "edit_revision": first["edit_revision"],
            "data_props": [{"name": "link", "datatype": "anyURI"}],
        },
    )
    assert response.status_code == 200
    second = response.json()
    assert second["synonyms"] == second["data_props"][0]["synonyms"] == aliases
    response = client.put(
        f"/entity-types/{entity.id}",
        json={
            "if_match": second["current_revision"],
            "edit_revision": second["edit_revision"],
            "synonyms": [],
            "data_props": [{"name": "link", "datatype": "anyURI", "synonyms": []}],
        },
    )
    assert response.status_code == 200
    assert (
        response.json()["synonyms"]
        == response.json()["data_props"][0]["synonyms"]
        == []
    )


def test_relation_synonyms_roundtrip_preserve_and_clear(
    client: TestClient, entity: ModelResource
) -> None:
    aliases = [{"language": "en-US", "text": "Peer"}]
    first = client.post(
        "/relations", json=relation_payload(entity, synonyms=aliases)
    ).json()
    assert first["synonyms"] == aliases
    second = client.put(f"/relations/{first['id']}", json={"if_match": 0}).json()
    assert second["synonyms"] == aliases
    third = client.put(
        f"/relations/{first['id']}",
        json={
            "if_match": 0,
            "edit_revision": second["edit_revision"],
            "synonyms": [],
        },
    ).json()
    assert third["synonyms"] == []


@pytest.mark.parametrize("rdf_format", list(OntologyExportFormat))
def test_any_uri_and_synonyms_frozen_rdf_restore_roundtrip(
    session: Session, entity: ModelResource, rdf_format: OntologyExportFormat
) -> None:
    aliases = [
        {"language": "zh-CN", "text": "人员"},
        {"language": "en-US", "text": "Human"},
    ]
    entity.synonyms = aliases
    set_data_props(
        session,
        entity,
        [
            DataTypePropCreate.model_validate(
                {
                    "name": "link",
                    "datatype": "anyURI",
                    "synonyms": aliases,
                    "label_i18n": {"zh-CN": "链接"},
                    "default_value": "https://example.org/文档",
                }
            )
        ],
    )
    publish_resource(session, entity)
    session.commit()
    snapshot = load_resource_snapshot(session, entity.id, 1)
    assert [item.model_dump() for item in snapshot.synonyms] == aliases
    entity.synonyms = []
    session.commit()
    assert load_resource_snapshot(session, entity.id, 1).synonyms == snapshot.synonyms
    snapshots = {entity.id: OntologyRdfResource.model_validate(snapshot.model_dump())}
    for reference in snapshot.resource_refs:
        child = load_resource_snapshot(session, reference.target_id, 1)
        snapshots[reference.target_id] = OntologyRdfResource.model_validate(
            child.model_dump()
        )
    metadata = OntologyRdfMetadata(
        name="People",
        iri="https://example.org/People",
        label_i18n={"zh-CN": "人员本体"},
        definition_i18n=None,
        synonyms=[Synonym.model_validate(item) for item in aliases],
    )
    content = serialize_ontology_rdf(
        metadata, snapshots, revision=1, rdf_format=rdf_format
    )
    graph = Graph().parse(data=content, format=rdf_format.value)
    prop = URIRef(f"{entity.iri}/link")
    assert (prop, RDFS.range, XSD.anyURI) in graph
    assert (URIRef(f"{prop}#shape"), SH.datatype, XSD.anyURI) in graph
    assert (prop, SKOS.altLabel, Literal("Human", lang="en-US")) in graph
    data = Graph()
    instance = URIRef("https://example.org/person/1")
    data.add((instance, RDF.type, URIRef(entity.iri)))
    data.add(
        (instance, prop, Literal("https://example.org/document", datatype=XSD.anyURI))
    )
    assert validate(data, shacl_graph=graph)[0] is True
    data.set((instance, prop, Literal(42)))
    assert validate(data, shacl_graph=graph)[0] is False
    document = parse_restore_document(rdf_format.value, content)
    assert document.issues == []
    assert document.unsupported_triples == []
    assert (
        document.metadata is not None
        and document.metadata.synonyms == metadata.synonyms
    )
    restored = next(
        resource for resource in document.resources if resource.iri == str(prop)
    )
    assert restored.datatype is not None and restored.datatype.datatype == "anyURI"
    assert restored.synonyms == snapshot.synonyms


def test_restore_does_not_silently_drop_invalid_synonyms() -> None:
    graph = Graph()
    ns = Namespace("https://example.org/kg#")
    graph.add((ns.Person, RDF.type, RDFS.Class))
    graph.add((ns.Person, SKOS.altLabel, Literal("Person", lang="de")))
    document = parse_restore_document("turtle", graph.serialize(format="turtle"))
    assert any(
        issue.params["reason"] == "unsupported_synonym_language"
        for issue in document.issues
    )


@pytest.mark.parametrize("rdf_format", list(OntologyExportFormat))
def test_ontology_synonyms_digest_freeze_export_and_restore(
    session: Session,
    entity: ModelResource,
    tmp_path: Path,
    rdf_format: OntologyExportFormat,
) -> None:
    aliases = [
        {"language": "zh-CN", "text": "人员资料"},
        {"language": "en-US", "text": "People records"},
    ]
    entity.label_i18n = {"zh-CN": "人员", "en-US": "Person"}
    set_data_props(
        session,
        entity,
        [
            DataTypePropCreate(
                name="link", datatype="anyURI", label_i18n={"zh-CN": "链接"}
            )
        ],
    )
    publish_resource(session, entity)
    ontology = create_ontology(
        session,
        OntologyCreate.model_validate(
            {
                "name": "People",
                "iri": "https://example.org/People",
                "label_i18n": {"zh-CN": "人员本体"},
                "synonyms": aliases,
                "ref_resource_ids": [entity.id],
            }
        ),
    )
    assert ontology.synonyms == aliases
    before = working_context(session, ontology).digest
    update_ontology(
        session,
        ontology,
        OntologyUpdate.model_validate(
            {
                "if_match": 0,
                "if_edit_match": ontology.edit_revision,
                "synonyms": [{"language": "en-US", "text": "Human records"}],
            }
        ),
    )
    assert working_context(session, ontology).digest != before
    update_ontology(
        session,
        ontology,
        OntologyUpdate.model_validate(
            {
                "if_match": 0,
                "if_edit_match": ontology.edit_revision,
                "synonyms": aliases,
            }
        ),
    )
    publish_ontology(session, ontology)
    session.commit()
    ontology.synonyms = []
    session.commit()
    exported = export_ontology(session, ontology.id, rdf_format).content
    parsed = parse_restore_document(rdf_format.value, exported)
    assert parsed.metadata is not None
    assert [item.model_dump() for item in parsed.metadata.synonyms] == aliases
    engine = create_engine(f"sqlite:///{tmp_path}/restored-aliases.db")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as destination:
            _, preview = inspect_restore(destination, rdf_format.value, exported)
            assert preview.can_apply, preview.conflicts
            restored = restore_ontology(
                destination,
                OntologyRestoreRequest(
                    format=rdf_format.value,
                    content=exported,
                    preview_digest=preview.preview_digest,
                ),
            )
            destination.commit()
            roundtrip = parse_restore_document(
                rdf_format.value,
                export_ontology(destination, restored.ontology_id, rdf_format).content,
            )
            assert roundtrip.metadata is not None
            assert roundtrip.metadata.synonyms == parsed.metadata.synonyms
    finally:
        engine.dispose()
