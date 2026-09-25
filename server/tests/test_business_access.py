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
