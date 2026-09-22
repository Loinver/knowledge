"""M-07：独立解析导出，验证快照冻结、标准语义与失败保护。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.v1.ontologies import router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import install_error_handler
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.relation_service import create_relation_type
from app.domain.status_service import get_revision, publish_resource
from app.domain.type_service import create_entity_type
from app.models.domain import Ontology, OntologyResourceRef, OntologyRevision
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import ModelResource, ResourceParent, ResourceRef
from app.schemas.ontology import OntologyCreate
from app.schemas.relation import EndpointSpec, RelationTypeCreate
from app.schemas.type import EntityTypeCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/export.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app = FastAPI()
    install_error_handler(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def published(session: Session) -> tuple[Ontology, dict[str, ModelResource]]:
    ns = register_namespace(session, "ex", "https://example.org/kg#")
    resources: dict[str, ModelResource] = {}
    for name in ("Person", "Employee", "Department"):
        resources[name] = create_entity_type(
            session,
            EntityTypeCreate(
                name=name,
                namespace_id=ns.id,
                label_i18n={"zh-CN": f"中文{name}", "en-US": name},
                definition_i18n={"zh-CN": "定义", "en-US": "Definition"},
                parent_ids=[resources["Person"].id] if name == "Employee" else [],
            ),
        )
    salary = ModelResource(
        name="Salary",
        iri=f"{ns.iri}Salary",
        kind=ResourceKind.DATATYPE_PROP,
        namespace_id=ns.id,
        definition_i18n={"datatype": "decimal", "zh-CN": "薪酬"},
    )
    session.add(salary)
    session.flush()
    resources["Salary"] = salary
    session.add(
        ResourceRef(
            source_id=resources["Employee"].id,
            target_id=salary.id,
            role="data_prop",
        )
    )
    relation = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksFor",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于", "en-US": "Works for"},
            domain_spec=EndpointSpec(type_id=resources["Employee"].id),
            range_spec=EndpointSpec(type_id=resources["Department"].id),
            enable_attributes=True,
        ),
    )
    resources["WorksFor"] = relation
    association = session.scalar(
        select(ModelResource).where(ModelResource.kind == ResourceKind.ASSOC)
    )
    assert association is not None
    resources["Association"] = association
    for resource in resources.values():
        publish_resource(session, resource)
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="HumanResources",
            iri="https://example.org/ontology/hr",
            label_i18n={"zh-CN": "人力资源", "en-US": "Human resources"},
            definition_i18n={"zh-CN": "人员与雇佣", "en-US": "People and employment"},
            ref_resource_ids=[resource.id for resource in resources.values()],
        ),
    )
    publish_ontology(session, ontology)
    session.commit()
    return ontology, resources


def test_formats_roundtrip_and_preserve_semantics(
    client: TestClient, published: tuple[Ontology, dict[str, ModelResource]]
) -> None:
    ontology, resources = published
    graphs = []
    for rdf_format, media_type, extension in (
        ("turtle", "text/turtle", "ttl"),
        ("json-ld", "application/ld+json", "jsonld"),
    ):
        response = client.get(
            f"/api/v1/ontologies/{ontology.id}/export?format={rdf_format}"
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(media_type)
        assert response.headers["content-disposition"] == (
            f'attachment; filename="HumanResources-r1.{extension}"'
        )
        # 独立 rdflib 解析响应文本，不调用被测导出器的图构造方法。
        graph = Graph().parse(data=response.text, format=rdf_format)
        again = Graph().parse(
            data=graph.serialize(format=rdf_format), format=rdf_format
        )
        assert isomorphic(graph, again)
        graphs.append(graph)
    assert isomorphic(*graphs)
    graph = graphs[0]
    employee = URIRef(resources["Employee"].iri)
    salary = URIRef(resources["Salary"].iri)
    relation = URIRef(resources["WorksFor"].iri)
    assert (URIRef(ontology.iri), RDF.type, OWL.Ontology) in graph
    assert (URIRef(ontology.iri), OWL.versionInfo, Literal("1")) in graph
    assert (
        URIRef(ontology.iri),
        RDFS.label,
        Literal("人力资源", lang="zh-Hans"),
    ) in graph
    assert (
        URIRef(ontology.iri),
        RDFS.label,
        Literal("Human resources", lang="en"),
    ) in graph
    assert (
        URIRef(ontology.iri),
        RDFS.comment,
        Literal("人员与雇佣", lang="zh-Hans"),
    ) in graph
    assert (
        URIRef(ontology.iri),
        RDFS.comment,
        Literal("People and employment", lang="en"),
    ) in graph
    assert (employee, RDF.type, OWL.Class) in graph
    assert (employee, RDFS.label, Literal("中文Employee", lang="zh-Hans")) in graph
    assert (employee, RDFS.label, Literal("Employee", lang="en")) in graph
    assert (employee, RDFS.comment, Literal("定义", lang="zh-Hans")) in graph
    assert (employee, RDFS.subClassOf, URIRef(resources["Person"].iri)) in graph
    assert (salary, RDF.type, OWL.DatatypeProperty) in graph
    assert (salary, RDFS.range, XSD.decimal) in graph
    assert (salary, RDFS.domain, employee) in graph
    assert (relation, RDF.type, OWL.ObjectProperty) in graph
    assert (relation, RDFS.domain, employee) in graph
    assert (relation, RDFS.range, URIRef(resources["Department"].iri)) in graph
    assert (
        relation,
        URIRef("urn:knowledge:ref:assoc_resource"),
        URIRef(resources["Association"].iri),
    ) in graph
    assert (
        URIRef(resources["Association"].iri),
        URIRef("urn:knowledge:semantics:resourceKind"),
        Literal("ASSOC"),
    ) in graph


def test_export_is_frozen_after_live_mutation_and_republication(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
) -> None:
    ontology, resources = published
    url = f"/api/v1/ontologies/{ontology.id}/export"
    before = client.get(url).text
    employee = resources["Employee"]
    assert employee.label_i18n is not None
    employee.label_i18n["zh-CN"] = "草稿就地修改"
    assert client.get(url).text == before
    employee.label_i18n = {"zh-CN": "新版员工", "en-US": "New employee"}
    parent = session.scalar(
        select(ResourceParent).where(ResourceParent.child_id == employee.id)
    )
    assert parent is not None
    parent.parent_id = resources["Department"].id
    employee.namespace.prefix = "changed"
    employee.namespace.iri = "https://example.org/changed#"
    employee.status = ResourceStatus.DRAFT
    publish_resource(session, employee)
    ontology.status = ResourceStatus.DRAFT
    session.commit()
    assert client.get(url).text == before
    assert get_revision(session, employee.id, 1).payload["namespace"]["prefix"] == "ex"
    publish_ontology(session, ontology)
    session.commit()
    assert client.get(f"{url}?revision=1").text == before
    assert "新版员工" in client.get(url).text
    assert client.get(f"{url}?revision=2").text == client.get(url).text


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("9999/export", 404, ErrorCode.RESOURCE_NOT_FOUND),
        ("{id}/export?revision=9999", 404, ErrorCode.REVISION_NOT_FOUND),
        ("{id}/export?revision=0", 422, None),
        ("{id}/export?format=xml", 422, None),
    ],
)
def test_export_rejects_invalid_owner_revision_and_format(
    client: TestClient,
    published: tuple[Ontology, dict[str, ModelResource]],
    path: str,
    status: int,
    code: ErrorCode | None,
) -> None:
    response = client.get(f"/api/v1/ontologies/{path.format(id=published[0].id)}")
    assert response.status_code == status
    if code is not None:
        assert response.json()["code"] == code


def test_never_published_ontology_has_no_export(
    client: TestClient, session: Session
) -> None:
    ontology = create_ontology(
        session,
        OntologyCreate(name="Draft", iri="https://example.org/draft", label_i18n={}),
    )
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 422
    assert response.json()["params"]["reason"] == "ontology_not_published"


@pytest.mark.parametrize("missing", ["parent_ids", "resource_refs", "namespace"])
def test_legacy_snapshot_never_reads_live_structure(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
    missing: str,
) -> None:
    ontology, resources = published
    revision = get_revision(session, resources["Employee"].id, 1)
    revision.payload = {k: v for k, v in revision.payload.items() if k != missing}
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 422
    assert response.json()["params"]["reason"] == "missing_snapshot_structure"
    assert response.json()["params"]["fields"] == [missing]


@pytest.mark.parametrize("datatype", [None, "invalid", "enum"])
def test_missing_or_unsupported_datatype_is_not_faked(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
    datatype: str | None,
) -> None:
    ontology, resources = published
    revision = get_revision(session, resources["Salary"].id, 1)
    revision.payload = {
        **revision.payload,
        "definition_i18n": {} if datatype is None else {"datatype": datatype},
    }
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 422
    assert response.json()["params"]["reason"] == "unsupported_datatype"


def test_missing_pin_and_incomplete_closure_rejected(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
) -> None:
    ontology, resources = published
    revision = session.scalar(select(OntologyRevision))
    assert revision is not None
    original = revision.resource_versions.copy()
    revision.resource_versions = {**original, str(resources["Employee"].id): 9999}
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.REVISION_NOT_FOUND
    revision.resource_versions = {
        rid: pinned
        for rid, pinned in original.items()
        if rid != str(resources["Person"].id)
    }
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 422
    assert response.json()["params"]["reason"] == "incomplete_snapshot_closure"


def test_live_ontology_members_are_not_used_for_export(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
) -> None:
    ontology, _ = published
    url = f"/api/v1/ontologies/{ontology.id}/export"
    before = client.get(url).text
    for ref in session.scalars(select(OntologyResourceRef)):
        session.delete(ref)
    session.commit()
    assert client.get(url).text == before


@pytest.mark.parametrize(
    ("role", "target", "reason"),
    [
        ("union_of", "Employee", "unsupported_reference_role"),
        ("relation_range", "Salary", "invalid_endpoint_kind"),
        (None, None, "missing_relation_endpoints"),
    ],
)
def test_incomplete_relation_semantics_are_not_silently_omitted(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
    role: str | None,
    target: str | None,
    reason: str,
) -> None:
    ontology, resources = published
    revision = get_revision(session, resources["WorksFor"].id, 1)
    refs = [
        ref
        for ref in revision.payload["resource_refs"]
        if ref["role"] != "relation_range"
    ]
    if role is not None and target is not None:
        refs.append({"role": role, "target_id": resources[target].id})
    revision.payload = {**revision.payload, "resource_refs": refs}
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 422
    assert response.json()["code"] == ErrorCode.VALIDATION_VIOLATION
    assert response.json()["params"]["reason"] == reason


@pytest.mark.parametrize("iri", ["not-an-iri", "https://[", "https://example.org/a b"])
def test_invalid_snapshot_ontology_iri_returns_structured_error(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
    iri: str,
) -> None:
    ontology, _ = published
    revision = session.scalar(select(OntologyRevision))
    assert revision is not None
    revision.metadata_snapshot = {**revision.metadata_snapshot, "iri": iri}
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 400
    assert response.json()["code"] == ErrorCode.INVALID_IRI


@pytest.mark.parametrize("rdf_format", ["turtle", "json-ld"])
def test_root_metadata_is_frozen_across_updates_and_publications(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
    rdf_format: str,
) -> None:
    ontology, _ = published
    url = f"/api/v1/ontologies/{ontology.id}/export?format={rdf_format}"
    before = client.get(url)
    assert ontology.label_i18n is not None
    assert ontology.definition_i18n is not None
    ontology.label_i18n["en-US"] = "In-place draft label"
    ontology.definition_i18n["en-US"] = "In-place draft definition"
    assert client.get(url).text == before.text
    updated = client.put(
        f"/api/v1/ontologies/{ontology.id}",
        json={
            "if_match": 1,
            "label_i18n": {"zh-CN": "新名称", "en-US": "Updated label"},
            "definition_i18n": {"zh-CN": "新定义", "en-US": "Updated definition"},
        },
    )
    assert updated.status_code == 200
    ontology.name = "Renamed"
    ontology.iri = "https://example.org/ontology/renamed"
    session.commit()
    assert client.get(url).text == before.text
    assert (
        client.get(url).headers["content-disposition"]
        == (before.headers["content-disposition"])
    )
    publish_ontology(session, ontology)
    session.commit()
    assert client.get(f"{url}&revision=1").text == before.text
    latest = client.get(url)
    assert "Renamed-r2" in latest.headers["content-disposition"]
    graph = Graph().parse(data=latest.text, format=rdf_format)
    assert (URIRef(ontology.iri), RDF.type, OWL.Ontology) in graph
    assert (
        URIRef(ontology.iri),
        RDFS.label,
        Literal("Updated label", lang="en"),
    ) in graph
    assert (
        URIRef(ontology.iri),
        RDFS.comment,
        Literal("Updated definition", lang="en"),
    ) in graph


@pytest.mark.parametrize(
    "field", [None, "name", "iri", "label_i18n", "definition_i18n"]
)
def test_missing_historical_header_never_uses_current_metadata(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
    field: str | None,
) -> None:
    ontology, _ = published
    revision = session.scalar(select(OntologyRevision))
    assert revision is not None
    revision.metadata_snapshot = (
        {}
        if field is None
        else {k: v for k, v in revision.metadata_snapshot.items() if k != field}
    )
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 422
    assert response.json()["code"] == ErrorCode.VALIDATION_VIOLATION
    assert response.json()["params"]["reason"] == "missing_ontology_metadata_snapshot"


def test_invalid_header_snapshot_returns_structured_error(
    client: TestClient,
    session: Session,
    published: tuple[Ontology, dict[str, ModelResource]],
) -> None:
    ontology, _ = published
    revision = session.scalar(select(OntologyRevision))
    assert revision is not None
    revision.metadata_snapshot = {**revision.metadata_snapshot, "label_i18n": []}
    session.commit()
    response = client.get(f"/api/v1/ontologies/{ontology.id}/export")
    assert response.status_code == 422
    assert response.json()["params"]["reason"] == "invalid_ontology_metadata_snapshot"


def test_metadata_migration_preserves_old_rows_and_replays(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path}/metadata-migration.db"
    environment = {**os.environ, "KG_DATABASE_URL": database_url}

    def migrate(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "0002_rule_library")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ontology (id, name, iri, status, current_revision) "
                "VALUES (1, 'Legacy', 'https://example.org/legacy', 'PUBLISHED', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO ontology_revision "
                "(id, ontology_id, revision, ref_domains, ref_types, rules, "
                "resource_versions) VALUES (1, 1, 1, '[]', '[17]', '[]', :versions)"
            ),
            {"versions": '{"17": 3}'},
        )
    migrate("upgrade", "0003_ontology_metadata")
    columns = {
        column["name"]: column
        for column in inspect(engine).get_columns("ontology_revision")
    }
    assert columns["metadata_snapshot"]["nullable"] is False
    with Session(engine) as db:
        revision = db.get(OntologyRevision, 1)
        assert revision is not None
        assert revision.metadata_snapshot == {}
        assert revision.resource_versions == {"17": 3}
        assert revision.ref_types == [17]
        # New ORM publications populate a complete header; old rows stay explicit.
        ontology = db.get(Ontology, 1)
        assert ontology is not None
        publish_ontology(db, ontology)
        db.commit()
        latest = db.scalar(
            select(OntologyRevision).where(OntologyRevision.revision == 2)
        )
        assert latest is not None
        assert latest.metadata_snapshot == {
            "name": "Legacy",
            "iri": "https://example.org/legacy",
            "label_i18n": None,
            "definition_i18n": None,
        }
    migrate("downgrade", "0002_rule_library")
    assert "metadata_snapshot" not in {
        column["name"] for column in inspect(engine).get_columns("ontology_revision")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT name FROM ontology")) == "Legacy"
        assert connection.scalar(text("SELECT count(*) FROM ontology_revision")) == 2
    migrate("upgrade", "0003_ontology_metadata")
    with Session(engine) as db:
        revisions = list(db.scalars(select(OntologyRevision)))
        assert len(revisions) == 2
        assert all(revision.metadata_snapshot == {} for revision in revisions)
        assert revisions[0].resource_versions == {"17": 3}
    engine.dispose()
