"""M-06 Turtle/JSON-LD 导入：安全预解析、冲突预览和显式解决。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from app.api.errors import install_error_handler
from app.api.v1.namespaces import router as namespaces_router
from app.api.v1.ontologies import router as ontologies_router
from app.api.v1.types import router as types_router
from app.core.db import Base, get_session
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import create_ontology
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.models.domain import Ontology
from app.models.enums import ResourceKind
from app.models.resource import ModelResource
from app.schemas.ontology import OntologyCreate
from app.schemas.ontology_import import ImportFormat
from app.schemas.type import EntityTypeCreate
from app.semantics.ontology_rdf import parse_ontology_rdf
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import Graph
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

URL = "/api/v1/ontologies"


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/import.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    def request_session() -> Iterator[Session]:
        with Session(session.get_bind(), expire_on_commit=False) as db:
            yield db

    app = FastAPI()
    for route in (namespaces_router, types_router, ontologies_router):
        app.include_router(route, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = request_session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def draft_ontology(
    session: Session,
) -> tuple[Ontology, ModelResource]:
    namespace = register_namespace(session, "ex", "https://example.org/kg#")
    entity = create_entity_type(
        session,
        EntityTypeCreate(
            name="Existing",
            namespace_id=namespace.id,
            label_i18n={"zh-CN": "已有类型", "en-US": "Existing"},
        ),
    )
    publish_resource(session, entity)
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="ImportTarget",
            iri="https://example.org/ontology/import-target",
            label_i18n={"zh-CN": "导入目标", "en-US": "Import target"},
        ),
    )
    session.commit()
    return ontology, entity


CONTENT = """@prefix ex: <https://example.org/kg#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:Existing a owl:Class ; rdfs:label "已有类型"@zh .
ex:Unknown a owl:Class ; rdfs:label "未知类型"@zh .
"""


def test_preview_reports_unknown_resource_and_apply_requires_explicit_resolution(
    client: TestClient, draft_ontology: tuple[Ontology, ModelResource]
) -> None:
    ontology, entity = draft_ontology
    preview = client.post(
        f"{URL}/import/preview",
        json={"format": "turtle", "content": CONTENT, "ontology_id": ontology.id},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["triple_count"] == 4
    assert body["requires_resolution"] is True
    assert {item["code"] for item in body["conflicts"]} == {"UNKNOWN_RESOURCE"}
    assert body["resources"][0]["existing_resource_id"] == entity.id

    unresolved = client.post(
        f"{URL}/{ontology.id}/import",
        headers={"If-Match": "0"},
        json={
            "ontology_id": ontology.id,
            "format": "turtle",
            "content": CONTENT,
            "resolutions": [],
        },
    )
    assert unresolved.status_code == 400
    assert unresolved.json()["code"] == "KG.INVALID_REQUEST"
    assert unresolved.json()["params"]["reason"] == "import_resolution_required"

    applied = client.post(
        f"{URL}/{ontology.id}/import",
        headers={"If-Match": "0"},
        json={
            "ontology_id": ontology.id,
            "format": "turtle",
            "content": CONTENT,
            "resolutions": [
                {
                    "iri": "https://example.org/kg#Unknown",
                    "action": "SKIP",
                }
            ],
        },
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["added_resource_ids"] == [entity.id]
    assert applied.json()["skipped_iris"] == ["https://example.org/kg#Unknown"]

    refs = client.get(f"{URL}/{ontology.id}/refs")
    assert refs.status_code == 200
    assert [ref["resource_id"] for ref in refs.json()] == [entity.id]


def test_import_requires_current_if_match_and_rejects_external_or_unsafe_rdf(
    client: TestClient, draft_ontology: tuple[Ontology, ModelResource]
) -> None:
    ontology, _ = draft_ontology
    missing_header = client.post(
        f"{URL}/{ontology.id}/import",
        json={
            "ontology_id": ontology.id,
            "format": "turtle",
            "content": CONTENT,
            "resolutions": [],
        },
    )
    assert missing_header.status_code == 400
    assert missing_header.json()["code"] == "KG.INVALID_REQUEST"

    external_context = client.post(
        f"{URL}/import/preview",
        json={
            "format": "json-ld",
            "content": '{"@context":"https://example.org/context.jsonld","@id":"https://example.org/kg#Existing"}',
        },
    )
    assert external_context.status_code == 422
    assert external_context.json()["code"] == "KG.VALIDATION_VIOLATION"
    assert external_context.json()["params"]["reason"] == "external_json_ld_context"

    imports = client.post(
        f"{URL}/import/preview",
        json={
            "format": "turtle",
            "content": (
                "@prefix owl: <http://www.w3.org/2002/07/owl#> . "
                "<https://example.org/o> owl:imports "
                "<https://example.org/remote> ."
            ),
        },
    )
    assert imports.status_code == 422
    assert imports.json()["params"]["reason"] == "owl_imports_not_allowed"

    stale = client.post(
        f"{URL}/{ontology.id}/import",
        headers={"If-Match": "9"},
        json={
            "ontology_id": ontology.id,
            "format": "turtle",
            "content": CONTENT,
            "resolutions": [],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "KG.REVISION_CONFLICT"


@pytest.mark.parametrize("rdf_format", ["turtle", "json-ld"])
def test_rdf_adapter_parses_members_and_labels_without_database(
    rdf_format: ImportFormat,
) -> None:
    graph = Graph().parse(
        data="""@prefix ex: <https://example.org/kg#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix kg: <urn:knowledge:semantics:> .
        <https://example.org/ontology/hr> a owl:Ontology .
        ex:Participation a owl:Class ; kg:resourceKind "ASSOC" ;
            rdfs:isDefinedBy <https://example.org/ontology/hr> ;
            rdfs:label "参与记录"@zh-Hans, "Participation"@en .
        ex:Unrelated a owl:Class .
        """,
        format="turtle",
    )
    parsed = parse_ontology_rdf(rdf_format, graph.serialize(format=rdf_format))
    assert parsed.root_iri == "https://example.org/ontology/hr"
    assert parsed.triple_count == len(graph)
    assert [resource.iri for resource in parsed.resources] == [
        "https://example.org/kg#Participation"
    ]
    resource = parsed.resources[0]
    assert resource.kind == ResourceKind.ASSOC
    assert resource.label_i18n == {"zh-CN": "参与记录", "en-US": "Participation"}
    assert resource.existing_resource_id is None
    assert resource.conflict_codes == []


@pytest.mark.parametrize(
    ("rdf_format", "content", "reason"),
    [
        ("turtle", "invalid RDF", "invalid_rdf"),
        ("json-ld", "{", "invalid_json_ld"),
        ("turtle", " " * 65_537, "import_too_large"),
        (
            "turtle",
            "@prefix ex: <urn:ex:> . "
            + " ".join(f"ex:s{i} ex:p ex:o ." for i in range(2_001)),
            "too_many_triples",
        ),
    ],
)
def test_rdf_adapter_preserves_import_limits(
    rdf_format: ImportFormat, content: str, reason: str
) -> None:
    with pytest.raises(KGError) as error:
        parse_ontology_rdf(rdf_format, content)
    assert error.value.params["reason"] == reason


@pytest.mark.parametrize(
    "document",
    [
        {"@graph": [{"@context": "https://example.org/context.jsonld"}]},
        {"@context": {"@import": "https://example.org/context.jsonld"}},
        {
            "@context": {
                "member": {
                    "@id": "urn:ex:member",
                    "@context": ["https://example.org/context.jsonld"],
                }
            }
        },
    ],
)
def test_nested_external_context_is_rejected_before_loading(document: object) -> None:
    with patch(
        "rdflib.plugins.shared.jsonld.context.source_to_json",
        side_effect=AssertionError("external context must not be loaded"),
    ) as loader:
        with pytest.raises(KGError) as error:
            parse_ontology_rdf("json-ld", json.dumps(document))
        assert error.value.params["reason"] == "external_json_ld_context"
        loader.assert_not_called()


@pytest.mark.parametrize("nested", [False, True])
def test_inline_jsonld_context_remains_supported(nested: bool) -> None:
    document = {
        "@context": {
            "owl": "http://www.w3.org/2002/07/owl#",
            "label": {
                "@id": "http://www.w3.org/2000/01/rdf-schema#label",
                "@container": "@language",
            },
        },
        "@id": "https://example.org/kg#Employee",
        "@type": "owl:Class",
        "label": {"zh-CN": "员工", "en-US": "Employee"},
    }
    content = json.dumps({"@graph": [document]} if nested else document)
    with patch(
        "rdflib.plugins.shared.jsonld.context.source_to_json",
        side_effect=AssertionError("inline context must not load external documents"),
    ) as loader:
        parsed = parse_ontology_rdf("json-ld", content)
        loader.assert_not_called()
    assert parsed.triple_count == 3
    assert parsed.resources[0].iri == "https://example.org/kg#Employee"
    assert parsed.resources[0].kind == ResourceKind.ENTITY
    assert parsed.resources[0].label_i18n == {"zh-CN": "员工", "en-US": "Employee"}


def test_import_edit_revision_is_atomic_and_rejects_stale_edits(
    client: TestClient, draft_ontology: tuple[Ontology, ModelResource]
) -> None:
    ontology, entity = draft_ontology
    url = f"{URL}/{ontology.id}"
    payload = {
        "ontology_id": ontology.id,
        "format": "turtle",
        "content": CONTENT,
        "resolutions": [{"iri": "https://example.org/kg#Unknown", "action": "SKIP"}],
    }
    before = client.get(url).json()
    token = before["edit_revision"]
    headers = {"If-Match": "0", "If-Edit-Match": str(token)}
    applied = client.post(f"{url}/import", headers=headers, json=payload)
    assert applied.status_code == 200, applied.text
    assert applied.json()["added_resource_ids"] == [entity.id]
    after = client.get(url).json()
    assert after["edit_revision"] == token + 1
    assert after["current_revision"] == 0

    stale = client.post(f"{url}/import", headers=headers, json=payload)
    assert stale.status_code == 409
    assert stale.json()["code"] == "KG.REVISION_CONFLICT"
    assert stale.json()["params"]["expected"] == token
    assert stale.json()["params"]["actual"] == token + 1
    failed = client.post(
        f"{url}/import",
        headers={"If-Match": "0", "If-Edit-Match": str(token + 1)},
        json={**payload, "content": "invalid RDF"},
    )
    assert failed.status_code == 422
    assert failed.json()["params"]["reason"] == "invalid_rdf"
    assert client.get(url).json()["edit_revision"] == token + 1
    assert [ref["resource_id"] for ref in client.get(f"{url}/refs").json()] == [
        entity.id
    ]
