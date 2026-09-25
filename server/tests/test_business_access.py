"""Business API access must be enforced by the server, not only by the UI."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.db import Base, get_session
from app.domain.account_service import bootstrap_admin, hash_password, issue_session
from app.main import app
from app.models.account import User
from app.models.enums import UserRole
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

API = "/api/v1"


@pytest.fixture()
def client_and_tokens(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str]]]:
    engine = create_engine(f"sqlite:///{tmp_path}/access.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    def request_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    with sessions() as session:
        admin = bootstrap_admin(
            session,
            username="admin",
            email="admin@example.org",
            password="admin-password-1",
        )
        tokens = {"ADMIN": issue_session(session, admin).access_token}
        for role in (UserRole.EDITOR, UserRole.VIEWER):
            name = role.value.lower()
            user = User(
                username=name,
                email=f"{name}@example.org",
                password_hash=hash_password("test-password-1"),
                role=role,
            )
            session.add(user)
            session.flush()
            tokens[role.value] = issue_session(session, user).access_token
        session.commit()

    app.dependency_overrides[get_session] = request_session
    try:
        yield TestClient(app), tokens
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_business_routes_require_authentication(
    client_and_tokens: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = client_and_tokens
    assert client.get(f"{API}/health").status_code == 200
    assert client.get(f"{API}/auth/config").status_code == 200
    for path in ("/namespaces", "/datasources", "/extraction/runs"):
        response = client.get(f"{API}{path}")
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH.TOKEN_EXPIRED"
    response = client.post(
        f"{API}/namespaces",
        json={"prefix": "anon", "iri": "https://example.org/anon/"},
    )
    assert response.status_code == 401


def test_viewer_can_read_but_only_editor_or_admin_can_write(
    client_and_tokens: tuple[TestClient, dict[str, str]],
) -> None:
    client, tokens = client_and_tokens
    namespace = {"prefix": "access", "iri": "https://example.org/access/"}
    viewer = {"Authorization": f"Bearer {tokens['VIEWER']}"}
    editor = {"Authorization": f"Bearer {tokens['EDITOR']}"}
    admin = {"Authorization": f"Bearer {tokens['ADMIN']}"}

    assert client.get(f"{API}/namespaces", headers=viewer).status_code == 200
    denied = client.post(f"{API}/namespaces", json=namespace, headers=viewer)
    assert denied.status_code == 403
    assert denied.json()["code"] == "AUTH.FORBIDDEN"
    created = client.post(f"{API}/namespaces", json=namespace, headers=editor)
    assert created.status_code == 201
    assert client.get(f"{API}/namespaces", headers=admin).status_code == 200


@pytest.mark.parametrize("role", ["VIEWER", "EDITOR", "ADMIN"])
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/ontologies",
            {
                "name": "AccessOntology",
                "iri": "https://example.org/access/ontology/",
                "label_i18n": {"zh-CN": "测试本体"},
            },
        ),
        (
            "/governance/templates",
            {
                "name": "AccessTemplate",
                "label_i18n": {"zh-CN": "测试模板"},
                "source": "ENTERPRISE",
                "basis": "Access regression fixture",
            },
        ),
        (
            "/governance/enum-dictionaries",
            {
                "name": "AccessEnum",
                "label_i18n": {"zh-CN": "测试枚举"},
                "definition_i18n": {"zh-CN": "访问控制测试"},
                "entries": [{"value": "A", "label_i18n": {"zh-CN": "甲"}}],
            },
        ),
        (
            "/governance/clauses",
            {
                "standard": "TEST",
                "clause_number": "1",
                "title_i18n": {"zh-CN": "测试条款"},
                "self_authored_description": {"zh-CN": "访问控制测试"},
            },
        ),
        (
            "/governance/rules",
            {
                "identifier": "AccessRule",
                "name_i18n": {"zh-CN": "测试规则"},
                "category": "TEST",
                "source_kind": "ENTERPRISE",
                "source_reference": "Access regression fixture",
                "target_iri": "https://example.org/Type",
                "severity": "VIOLATION",
                "language": "SHACL",
                "expression": (
                    "@prefix sh: <http://www.w3.org/ns/shacl#> . "
                    "<https://example.org/Shape> a sh:NodeShape; "
                    "sh:targetClass <https://example.org/Type>; "
                    "sh:property [sh:path <https://example.org/name>; sh:minCount 1] ."
                ),
                "execution": "MANUAL",
                "positive_example": (
                    "<https://example.org/a> a <https://example.org/Type>; "
                    '<https://example.org/name> "Example" .'
                ),
                "negative_example": (
                    "<https://example.org/b> a <https://example.org/Type> ."
                ),
            },
        ),
    ],
)
def test_authenticated_writes_can_start_their_own_transaction(
    client_and_tokens: tuple[TestClient, dict[str, str]],
    role: str,
    path: str,
    payload: dict[str, object],
) -> None:
    client, tokens = client_and_tokens
    headers = {"Authorization": f"Bearer {tokens[role]}"}
    response = client.post(f"{API}{path}", headers=headers, json=payload)
    if role == "VIEWER":
        assert response.status_code == 403
        return
    assert response.status_code == 201, response.text
    resource_id = response.json()["id"]
    saved = client.get(f"{API}{path}/{resource_id}", headers=headers)
    assert saved.status_code == 200
    assert saved.json()["id"] == resource_id


def test_business_auth_rechecks_roles_and_rejects_invalid_tokens(
    client_and_tokens: tuple[TestClient, dict[str, str]],
) -> None:
    client, tokens = client_and_tokens
    editor = {"Authorization": f"Bearer {tokens['EDITOR']}"}
    admin = {"Authorization": f"Bearer {tokens['ADMIN']}"}
    user = client.get(f"{API}/auth/me", headers=editor).json()
    payload = {
        "name": "BeforeDowngrade",
        "iri": "https://example.org/before/",
        "label_i18n": {"zh-CN": "降级前"},
    }
    created = client.post(f"{API}/ontologies", headers=editor, json=payload)
    assert created.status_code == 201
    changed = client.patch(
        f"{API}/users/{user['id']}", headers=admin, json={"role": "VIEWER"}
    )
    assert changed.status_code == 200
    denied = client.post(f"{API}/ontologies", headers=editor, json=payload)
    assert denied.status_code == 403
    assert client.get(f"{API}/ontologies", headers=editor).status_code == 200
    invalid = client.get(
        f"{API}/ontologies", headers={"Authorization": "Bearer invalid-token"}
    )
    assert invalid.status_code == 401
