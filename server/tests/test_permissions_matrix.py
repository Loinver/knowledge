"""逐角色 × 逐路由权限矩阵（第三批 P1-05）。

必测断言（对四类账号全矩阵校验，不凭单路由推断）：
- 匿名（无令牌）：所有业务/系统路由 401
- VIEWER：业务路由 GET 200、非读 403、系统管理 403
- EDITOR：业务路由读/写 200、系统管理 403
- ADMIN：全部 200
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.errors import install_error_handler
from app.core.db import Base, get_session
from app.domain.account_service import hash_password, issue_session
from app.main import app
from app.models.account import User
from app.models.enums import UserRole
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ADMIN = ("matrix_admin", "Matrix-Admin-2026!", UserRole.ADMIN)
EDITOR = ("matrix_editor", "Matrix-Editor-2026!", UserRole.EDITOR)
VIEWER = ("matrix_viewer", "Matrix-Viewer-2026!", UserRole.VIEWER)


@pytest.fixture()
def client_and_tokens(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str]]]:
    engine = create_engine(f"sqlite:///{tmp_path}/matrix.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        tokens: dict[str, str] = {}
        for account, password, role in (ADMIN, EDITOR, VIEWER):
            user = User(
                username=account,
                email=f"{account}@example.org",
                password_hash=hash_password(password),
                role=role,
            )
            db.add(user)
            db.flush()
            tokens[role.value] = issue_session(db, user).access_token
        db.commit()

        def request_session() -> Iterator[Session]:
            with factory() as request_db:
                yield request_db

        app.dependency_overrides[get_session] = request_session
        install_error_handler(app)
        try:
            with TestClient(app) as test_client:
                yield test_client, tokens
        finally:
            app.dependency_overrides.pop(get_session, None)
            engine.dispose()


def _register_matrix() -> list[tuple[str, str, set[str]]]:
    """(方法, 路径, 允许通过的最低角色集合)。路径参数用最小占位资源。"""
    return [
        ("GET", "/api/v1/namespaces", {"VIEWER", "EDITOR", "ADMIN"}),
        ("POST", "/api/v1/namespaces", {"EDITOR", "ADMIN"}),
        ("GET", "/api/v1/entity-types", {"VIEWER", "EDITOR", "ADMIN"}),
        ("POST", "/api/v1/entity-types", {"EDITOR", "ADMIN"}),
        ("GET", "/api/v1/relations", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/domains", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/ontologies", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/mappings", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/datasources", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/governance/rules", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/governance/clauses", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/governance/enums", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/extraction/runs", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/extraction/tasks", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/extraction/graph/revisions", {"VIEWER", "EDITOR", "ADMIN"}),
        ("POST", "/api/v1/extraction/runs", {"EDITOR", "ADMIN"}),
        ("POST", "/api/v1/extraction/graph/1/switch", {"EDITOR", "ADMIN"}),
        ("GET", "/api/v1/validation/reports/1", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/dashboard/stats", {"VIEWER", "EDITOR", "ADMIN"}),
        ("GET", "/api/v1/users", {"ADMIN"}),
        ("GET", "/api/v1/roles", {"ADMIN"}),
        ("GET", "/api/v1/audit-logs", {"ADMIN"}),
        ("GET", "/api/v1/view-templates", {"VIEWER", "EDITOR", "ADMIN"}),
        ("POST", "/api/v1/view-templates", {"EDITOR", "ADMIN"}),
    ]


def test_permission_matrix(client_and_tokens) -> None:
    client, role_tokens = client_and_tokens
    tokens = {"ANONYMOUS": None, **role_tokens}
    violations: list[str] = []
    for method, path, allowed in _register_matrix():
        for role, token in tokens.items():
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            response = client.request(method, path, headers=headers)
            # 判据：401/403 = 鉴权拒绝；其余（200/404/422 等）= 已过鉴权
            denied = response.status_code in (401, 403)
            expected_denied = role == "ANONYMOUS" or role not in allowed
            if denied != expected_denied:
                violations.append(
                    f"{role:9s} {method:4s} {path} -> {response.status_code} "
                    f"(expected {'denied' if expected_denied else 'pass'})"
                )
    assert not violations, "权限矩阵越界：\n" + "\n".join(violations)


def test_viewer_cannot_write_any_business_route(client_and_tokens) -> None:
    """VIEWER 对所有非读业务路由 403（写保护全覆盖，不只抽样）。"""
    client, role_tokens = client_and_tokens
    headers = {"Authorization": f"Bearer {role_tokens['VIEWER']}"}
    write_paths = [
        ("/api/v1/namespaces", {"prefix": "x", "iri": "https://x.example.org/"}),
        ("/api/v1/entity-types", {"name": "X", "namespace_id": 1, "data_props": []}),
        ("/api/v1/mappings", {"name": "x", "ontology_id": 1}),
        ("/api/v1/extraction/runs", {"mapping_revision_id": 1, "datasource_id": 1}),
        (
            "/api/v1/view-templates",
            {
                "name_i18n": {"zh-CN": "x"},
                "layout_id": "ring",
                "ontology_id": 1,
                "ontology_revision": 1,
            },
        ),
    ]
    for path, payload in write_paths:
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 403, f"{path} -> {response.status_code}"


def test_editor_cannot_access_admin_routes(client_and_tokens) -> None:
    client, role_tokens = client_and_tokens
    headers = {"Authorization": f"Bearer {role_tokens['EDITOR']}"}
    for path in ("/api/v1/users", "/api/v1/roles", "/api/v1/audit-logs"):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, f"{path} -> {response.status_code}"


def test_anonymous_is_401_everywhere(client_and_tokens) -> None:
    """未认证访问任何业务/系统路由 → 401（统一鉴权依赖生效）。"""
    client, _tokens = client_and_tokens
    for method, path, _allowed in _register_matrix():
        response = client.request(method, path)
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
