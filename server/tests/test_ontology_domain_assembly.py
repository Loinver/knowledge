"""业务域独立 ID、冻结成员版本和 HTTP 装配事务回归。"""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import pytest
from app.api.v1.ontologies import add_domain_members_endpoint
from app.core.db import Base, get_session
from app.domain.account_service import issue_session
from app.domain.domain_service import (
    add_member,
    create_domain,
    list_members,
    publish_domain,
    remove_member,
)
from app.domain.iri_service import register_namespace
from app.domain.ontology_service import create_ontology, list_refs
from app.domain.resource_lifecycle import unpublish_resource
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.main import app
from app.models.account import User
from app.models.asset_audit import AssetAuditAction, AssetType
from app.models.domain import (
    BusinessDomain,
    DomainRevision,
    Ontology,
    OntologyResourceRef,
)
from app.models.enums import UserRole
from app.models.resource import ModelResource, ResourceRevision
from app.schemas.domain import DomainCreate, DomainMemberAdd
from app.schemas.ontology import OntologyCreate
from app.schemas.type import EntityTypeCreate
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker


@dataclass
class AssemblyCase:
    client: TestClient
    sessions: sessionmaker[Session]
    ids: dict[str, int]
    tokens: dict[str, str]

    def state(self) -> tuple[int, dict[int, int | None]]:
        with self.sessions() as db:
            ontology = db.get(Ontology, self.ids["ontology"])
            assert ontology is not None
            return ontology.edit_revision, {
                ref.resource_id: ref.pinned_revision
                for ref in list_refs(db, ontology.id)
            }

    def assemble(self, role: str | None = "EDITOR", **overrides: int) -> Response:
        headers = {"Authorization": f"Bearer {self.tokens[role]}"} if role else {}
        return self.client.post(
            f"/api/v1/ontologies/{self.ids['ontology']}/domain-members",
            headers=headers,
            json={
                "domain_id": self.ids["domain"],
                "domain_revision": 1,
                "if_edit_match": self.state()[0],
                **overrides,
            },
        )


def make_type(db: Session, namespace_id: int, name: str) -> ModelResource:
    resource = create_entity_type(
        db,
        EntityTypeCreate(
            name=name,
            namespace_id=namespace_id,
            label_i18n={"en-US": name},
        ),
    )
    publish_resource(db, resource)
    return resource


def upgrade(db: Session, resource_id: int) -> None:
    resource = db.get(ModelResource, resource_id)
    assert resource is not None
    unpublish_resource(db, resource)
    resource.label_i18n = {"en-US": "Second published version"}
    publish_resource(db, resource)


@pytest.fixture()
def case(tmp_path: Path) -> Iterator[AssemblyCase]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/assembly.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    tokens: dict[str, str] = {}
    with sessions() as db:
        ns = register_namespace(db, "assembly", "https://example.org/assembly/")
        unrelated = create_entity_type(
            db,
            EntityTypeCreate(
                name="UnrelatedDraft",
                namespace_id=ns.id,
                label_i18n={"en-US": "Unrelated"},
            ),
        )
        first = make_type(db, ns.id, "Employee")
        second = make_type(db, ns.id, "Department")
        domain = create_domain(
            db,
            DomainCreate(
                name="BusinessDomain",
                iri="https://example.org/domain/",
                label_i18n={"en-US": "Domain"},
                member_ids=[first.id, second.id],
            ),
        )
        assert domain.id == unrelated.id
        publish_domain(db, domain, domain.edit_revision)
        onto = create_ontology(
            db,
            OntologyCreate(
                name="TargetOntology",
                iri="https://example.org/ontology/",
                label_i18n={"en-US": "Ontology"},
            ),
        )
        ids = {
            "namespace": ns.id,
            "domain": domain.id,
            "ontology": onto.id,
            "first": first.id,
            "second": second.id,
            "unrelated": unrelated.id,
        }
        for role in (UserRole.EDITOR, UserRole.VIEWER, UserRole.ADMIN):
            user = User(
                username=role.value.lower(),
                email=f"{role.value}@example.org",
                password_hash="unused-test-only",
                role=role,
            )
            db.add(user)
            db.flush()
            tokens[role.value] = issue_session(db, user).access_token
        db.commit()

    def request_session() -> Iterator[Session]:
        with sessions() as db:
            yield db

    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = request_session
    client = TestClient(app)  # No lifespan: never initializes the development database.
    try:
        yield AssemblyCase(client, sessions, ids, tokens)
    finally:
        client.close()
        if previous is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous
        engine.dispose()


def test_published_pins_and_domain_id_collision(case: AssemblyCase) -> None:
    with case.sessions() as db:
        frozen = db.scalar(select(DomainRevision))
        assert frozen is not None
        assert frozen.payload["members"] == [
            {"resource_id": case.ids[key], "as_ref": False, "pinned_revision": 1}
            for key in ("first", "second")
        ]
    response = case.assemble()
    assert response.status_code == 200, response.text
    refs = response.json()
    assert {ref["resource_id"]: ref["pinned_revision"] for ref in refs} == {
        case.ids["first"]: 1,
        case.ids["second"]: 1,
    }
    edit, saved = case.state()
    assert edit == 1 and len(saved) == 2
    assert case.ids["unrelated"] not in saved
    spec = add_domain_members_endpoint.asset_audit_spec
    assert spec.action == AssetAuditAction.ASSEMBLE
    assert spec.object_type == AssetType.ONTOLOGY


def test_old_revision_and_idempotent_assembly(case: AssemblyCase) -> None:
    with case.sessions() as db:
        old = db.scalar(select(DomainRevision))
        assert old is not None
        snapshot = deepcopy(old.payload)
        domain = db.get(BusinessDomain, case.ids["domain"])
        assert domain is not None
        upgrade(db, case.ids["first"])
        membership = next(
            m
            for m in list_members(db, domain.id)
            if m.resource_id == case.ids["second"]
        )
        remove_member(db, domain.id, membership.id, domain.edit_revision)
        replacement = make_type(db, case.ids["namespace"], "NewMember")
        add_member(
            db,
            domain.id,
            DomainMemberAdd(
                resource_id=replacement.id,
                if_edit_match=domain.edit_revision,
            ),
        )
        publish_domain(db, domain, domain.edit_revision)
        db.commit()
        assert old.payload == snapshot
        latest = db.scalar(select(DomainRevision).where(DomainRevision.revision == 2))
        assert latest is not None
        assert {
            m["resource_id"]: m["pinned_revision"] for m in latest.payload["members"]
        } == {
            case.ids["first"]: 2,
            replacement.id: 1,
        }
    first = case.assemble()
    assert first.status_code == 200, first.text
    repeated = case.assemble()
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()
    assert case.state() == (2, {case.ids["first"]: 1, case.ids["second"]: 1})


@pytest.mark.parametrize("changed", [False, True])
def test_unpinned_refs_require_matching_current_version(
    case: AssemblyCase, changed: bool
) -> None:
    with case.sessions() as db:
        unrelated = make_type(db, case.ids["namespace"], "ExistingReference")
        db.add_all(
            [
                OntologyResourceRef(
                    ontology_id=case.ids["ontology"],
                    resource_id=case.ids["first"],
                    pinned_revision=None,
                ),
                OntologyResourceRef(
                    ontology_id=case.ids["ontology"],
                    resource_id=unrelated.id,
                    pinned_revision=1,
                ),
            ]
        )
        if changed:
            upgrade(db, case.ids["first"])
        db.commit()
    before = case.state()
    response = case.assemble()
    if changed:
        assert response.status_code == 409
        assert response.json()["code"] == "KG.REVISION_CONFLICT"
        assert case.state() == before
    else:
        assert response.status_code == 200, response.text
        assert {ref["resource_id"] for ref in response.json()} == {
            case.ids["first"],
            case.ids["second"],
        }
        assert case.state() == (
            1,
            {case.ids["first"]: 1, case.ids["second"]: 1, unrelated.id: 1},
        )


@pytest.mark.parametrize(
    "failure",
    [
        "legacy",
        "empty",
        "resource_missing",
        "revision_missing",
        "pin_conflict",
        "domain_missing",
        "domain_revision_missing",
        "stale_edit",
    ],
)
def test_route_failure_rolls_back_all_refs_and_edit_token(
    case: AssemblyCase, failure: str
) -> None:
    overrides: dict[str, int] = {}
    with case.sessions() as db:
        revision = db.scalar(select(DomainRevision))
        assert revision is not None
        if failure == "legacy":
            revision.payload = {
                **revision.payload,
                "members": [
                    {"resource_id": case.ids[key], "as_ref": False}
                    for key in ("first", "second")
                ],
            }
        elif failure == "empty":
            revision.payload = {**revision.payload, "members": []}
        elif failure == "resource_missing":
            revision.payload = {
                **revision.payload,
                "members": [
                    *revision.payload["members"],
                    {"resource_id": 9999, "pinned_revision": 1},
                ],
            }
        elif failure == "revision_missing":
            db.execute(
                delete(ResourceRevision).where(
                    ResourceRevision.resource_id == case.ids["second"],
                )
            )
        elif failure == "pin_conflict":
            upgrade(db, case.ids["second"])
            db.add(
                OntologyResourceRef(
                    ontology_id=case.ids["ontology"],
                    resource_id=case.ids["second"],
                    pinned_revision=2,
                )
            )
        elif failure == "domain_missing":
            overrides["domain_id"] = 9999
        elif failure == "domain_revision_missing":
            overrides["domain_revision"] = 99
        else:
            overrides["if_edit_match"] = 99
        # A matching unpinned earlier member must not become pinned on later failure.
        db.add(
            OntologyResourceRef(
                ontology_id=case.ids["ontology"],
                resource_id=case.ids["first"],
                pinned_revision=None,
            )
        )
        db.commit()
        historical_payload = deepcopy(revision.payload)
    before = case.state()
    response = case.assemble(**overrides)
    expected = {
        "legacy": (422, "KG.VALIDATION_VIOLATION"),
        "empty": (422, "KG.VALIDATION_VIOLATION"),
        "resource_missing": (404, "KG.RESOURCE_NOT_FOUND"),
        "revision_missing": (404, "KG.REVISION_NOT_FOUND"),
        "pin_conflict": (409, "KG.REVISION_CONFLICT"),
        "domain_missing": (404, "KG.RESOURCE_NOT_FOUND"),
        "domain_revision_missing": (404, "KG.REVISION_NOT_FOUND"),
        "stale_edit": (409, "KG.REVISION_CONFLICT"),
    }[failure]
    assert (response.status_code, response.json()["code"]) == expected
    assert case.state() == before
    if failure == "legacy":
        assert (
            response.json()["params"]["reason"] == "domain_member_versions_unavailable"
        )
        with case.sessions() as db:
            domain = db.get(BusinessDomain, case.ids["domain"])
            assert domain is not None
            publish_domain(db, domain, domain.edit_revision)
            db.commit()
            old = db.scalar(select(DomainRevision).where(DomainRevision.revision == 1))
            assert old is not None and old.payload == historical_payload


@pytest.mark.parametrize("role", [None, "VIEWER", "EDITOR", "ADMIN"])
def test_route_authorization_and_payload_bounds(
    case: AssemblyCase, role: str | None
) -> None:
    before = case.state()
    response = case.assemble(role)
    if role in {"EDITOR", "ADMIN"}:
        assert response.status_code == 200, response.text
        for overrides in (
            {"domain_id": 0},
            {"domain_revision": 0},
            {"if_edit_match": -1},
        ):
            state = case.state()
            assert case.assemble(role, **overrides).status_code == 422
            assert case.state() == state
    else:
        assert response.status_code == (401 if role is None else 403)
        assert case.state() == before
