"""HTTP and persistence coverage for administrator-managed model configs."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.api.errors import install_error_handler
from app.api.v1.ai_model_configs import router
from app.core.crypto import decrypt
from app.core.db import Base, get_session
from app.domain.account_service import bootstrap_admin, hash_password, issue_session
from app.domain.ai_model_service import is_current, resolve_default
from app.models.account import User
from app.models.ai_model import AiModelCapability, AiModelConfig, AiModelDefault
from app.models.enums import UserRole
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

API = "/api/v1/ai"
SECRET = "model-key-sensitive-value"


@pytest.fixture()
def client_and_tokens(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, dict[str, str], sessionmaker[Session]]]:
    engine = __import__("sqlalchemy").create_engine(f"sqlite:///{tmp_path}/models.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        admin = bootstrap_admin(
            session,
            username="admin",
            email="admin@example.org",
            password="admin-password-1",
        )
        tokens = {"ADMIN": issue_session(session, admin).access_token}
        for role in (UserRole.EDITOR, UserRole.VIEWER):
            username = role.value.lower()
            user = User(
                username=username,
                email=f"{username}@example.org",
                password_hash=hash_password("test-password-1"),
                role=role,
            )
            session.add(user)
            session.flush()
            tokens[role.value] = issue_session(session, user).access_token
        defaults = [
            AiModelDefault(capability=capability, config_id=None, revision=1)
            for capability in (AiModelCapability.CHAT, AiModelCapability.EMBEDDING)
        ]
        session.add_all(defaults)
        session.commit()

    def request_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    test_app = FastAPI()
    install_error_handler(test_app)
    test_app.include_router(router, prefix="/api/v1")
    test_app.dependency_overrides[get_session] = request_session
    try:
        with TestClient(test_app) as client:
            yield client, tokens, sessions
    finally:
        engine.dispose()


def headers(tokens: dict[str, str], role: str = "ADMIN") -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens[role]}"}


def create_config(
    client: TestClient,
    tokens: dict[str, str],
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Primary Chat",
        "capability": "CHAT",
        "base_url": "https://provider.example/v1/",
        "model": "chat-model",
        "api_key": SECRET,
        "enabled": True,
    }
    payload.update(overrides)
    response = client.post(
        f"{API}/model-configs", headers=headers(tokens), json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_search_matches_name_or_model_with_consistent_pagination(
    client_and_tokens: tuple[TestClient, dict[str, str], sessionmaker[Session]],
) -> None:
    client, tokens, _sessions = client_and_tokens
    by_model = create_config(client, tokens, model="fixture-needle-model")
    by_name = create_config(client, tokens, name="Needle Backup", enabled=False)
    create_config(client, tokens, name="Unrelated", model="unrelated-model")

    found: list[int] = []
    for page in (1, 2):
        response = client.get(
            f"{API}/model-configs",
            headers=headers(tokens),
            params={"q": "NEEDLE", "page": page, "page_size": 1, "sort": "id"},
        )
        assert response.status_code == 200
        assert response.json()["total"] == 2
        found.extend(item["id"] for item in response.json()["items"])
    assert found == [by_model["id"], by_name["id"]]
    filtered = client.get(
        f"{API}/model-configs",
        headers=headers(tokens),
        params={"q": "needle", "enabled": True},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert [item["id"] for item in filtered.json()["items"]] == [by_model["id"]]


def test_admin_crud_encrypts_and_never_returns_secret(
    client_and_tokens: tuple[TestClient, dict[str, str], sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, tokens, sessions = client_and_tokens
    calls: list[str] = []

    async def forbidden_model_call(*_args: Any, **_kwargs: Any) -> str:
        calls.append("called")
        raise AssertionError("configuration CRUD must not call a model")

    monkeypatch.setattr("app.core.ai_client.CompatibleModel.chat", forbidden_model_call)
    created = create_config(client, tokens)
    assert created["has_key"] is True
    assert created["api_key_mask"] == "***"
    assert "api_key" not in created and "credential_cipher" not in created
    with sessions() as session:
        row = session.get(AiModelConfig, created["id"])
        assert row is not None and row.credential_cipher != SECRET
        assert decrypt(row.credential_cipher or "") == SECRET

    fetched = client.get(
        f"{API}/model-configs/{created['id']}", headers=headers(tokens)
    )
    assert fetched.status_code == 200
    assert fetched.json()["api_key_mask"] == "***"
    assert SECRET not in fetched.text

    retained = client.put(
        f"{API}/model-configs/{created['id']}",
        headers={**headers(tokens), "If-Match": "1"},
        json={"model": "chat-model-v2"},
    )
    assert retained.status_code == 200
    assert retained.json()["has_key"] is True
    assert retained.json()["revision"] == 2

    replaced = client.put(
        f"{API}/model-configs/{created['id']}",
        headers={**headers(tokens), "If-Match": '"2"'},
        json={"api_key": "replacement-secret"},
    )
    assert replaced.status_code == 200
    with sessions() as session:
        row = session.get(AiModelConfig, created["id"])
        assert (
            row is not None
            and decrypt(row.credential_cipher or "") == "replacement-secret"
        )
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", None),
        ("base_url", None),
        ("model", None),
        ("timeout_seconds", None),
        ("model_version", None),
        ("enabled", None),
    ],
)
def test_update_rejects_explicit_null_non_secret_fields(
    client_and_tokens: tuple[TestClient, dict[str, str], sessionmaker[Session]],
    field: str,
    value: Any,
) -> None:
    client, tokens, sessions = client_and_tokens
    created = create_config(client, tokens)
    response = client.put(
        f"{API}/model-configs/{created['id']}",
        headers={**headers(tokens), "If-Match": "1"},
        json={field: value},
    )
    assert response.status_code == 422
    with sessions() as session:
        row = session.get(AiModelConfig, created["id"])
        assert row is not None and row.revision == 1


@pytest.mark.parametrize(
    "base_url",
    [
        "https://provider.example:invalid/v1",
        "https://provider.example:65536/v1",
        "https://provider .example/v1",
        "https://provider.example/v1\nheader",
    ],
)
def test_base_url_rejects_invalid_host_or_port(
    client_and_tokens: tuple[TestClient, dict[str, str], sessionmaker[Session]],
    base_url: str,
) -> None:
    client, tokens, _sessions = client_and_tokens
    response = client.post(
        f"{API}/model-configs",
        headers=headers(tokens),
        json={
            "name": "Invalid URL",
            "capability": "CHAT",
            "base_url": base_url,
            "model": "model",
        },
    )
    assert response.status_code == 422


def test_default_resolution_and_staleness_guard(
    client_and_tokens: tuple[TestClient, dict[str, str], sessionmaker[Session]],
) -> None:
    client, tokens, sessions = client_and_tokens
    created = create_config(client, tokens)
    selected = client.put(
        f"{API}/model-defaults/CHAT",
        headers={**headers(tokens), "If-Match": "1"},
        json={"config_id": created["id"]},
    )
    assert selected.status_code == 200
    with sessions() as session:
        resolved = resolve_default(session, AiModelCapability.CHAT)
        assert resolved is not None
        assert resolved.endpoint.api_key == SECRET
        assert is_current(session, resolved)

    updated = client.put(
        f"{API}/model-configs/{created['id']}",
        headers={**headers(tokens), "If-Match": "1"},
        json={"model": "replacement-model"},
    )
    assert updated.status_code == 200
    with sessions() as session:
        assert resolved is not None and not is_current(session, resolved)
        current = resolve_default(session, AiModelCapability.CHAT)
        assert current is not None and current.endpoint.model == "replacement-model"


def test_origin_change_requires_key_and_explicit_clear_disables_default(
    client_and_tokens: tuple[TestClient, dict[str, str], sessionmaker[Session]],
) -> None:
    client, tokens, sessions = client_and_tokens
    created = create_config(client, tokens)
    config_id = created["id"]
    default = client.put(
        f"{API}/model-defaults/CHAT",
        headers={**headers(tokens), "If-Match": "1"},
        json={"config_id": config_id},
    )
    assert default.status_code == 200

    changed_host = client.put(
        f"{API}/model-configs/{config_id}",
        headers={**headers(tokens), "If-Match": "1"},
        json={"base_url": "https://other.example/v1"},
    )
    assert changed_host.status_code == 400
    assert (
        changed_host.json()["params"]["reason"] == "api_key_required_for_origin_change"
    )

    cleared = client.put(
        f"{API}/model-configs/{config_id}",
        headers={**headers(tokens), "If-Match": "1"},
        json={"api_key": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["enabled"] is False
    assert cleared.json()["has_key"] is False
    with sessions() as session:
        row = session.scalar(
            select(AiModelDefault).where(
                AiModelDefault.capability == AiModelCapability.CHAT
            )
        )
        assert row is not None and row.config_id is None and row.revision == 3


def test_revisions_defaults_permissions_and_restart_persistence(
    client_and_tokens: tuple[TestClient, dict[str, str], sessionmaker[Session]],
) -> None:
    client, tokens, sessions = client_and_tokens
    for role in ("EDITOR", "VIEWER"):
        auth = headers(tokens, role)
        assert client.get(f"{API}/model-configs", headers=auth).status_code == 403
        assert (
            client.post(f"{API}/model-configs", headers=auth, json={}).status_code
            == 403
        )
        assert client.get(f"{API}/model-defaults", headers=auth).status_code == 403
        assert (
            client.put(
                f"{API}/model-defaults/CHAT",
                headers={**auth, "If-Match": "1"},
                json={"config_id": None},
            ).status_code
            == 403
        )

    created = create_config(client, tokens)
    wrong_capability = client.put(
        f"{API}/model-defaults/EMBEDDING",
        headers={**headers(tokens), "If-Match": "1"},
        json={"config_id": created["id"]},
    )
    assert wrong_capability.status_code == 400

    stale = client.put(
        f"{API}/model-configs/{created['id']}",
        headers={**headers(tokens), "If-Match": "9"},
        json={"model": "stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["params"] == {
        "resource": "ai_model_config",
        "expected": 1,
        "actual": 9,
    }

    selected = client.put(
        f"{API}/model-defaults/CHAT",
        headers={**headers(tokens), "If-Match": "1"},
        json={"config_id": created["id"]},
    )
    assert selected.status_code == 200
    with sessions() as reopened:
        item = reopened.get(AiModelConfig, created["id"])
        default = reopened.get(AiModelDefault, AiModelCapability.CHAT)
        assert item is not None and item.enabled and item.credential_cipher
        assert default is not None and default.config_id == item.id

    deleted = client.delete(
        f"{API}/model-configs/{created['id']}",
        headers={**headers(tokens), "If-Match": "1"},
    )
    assert deleted.status_code == 200
    with sessions() as reopened:
        default = reopened.get(AiModelDefault, AiModelCapability.CHAT)
        assert (
            default is not None and default.config_id is None and default.revision == 3
        )
