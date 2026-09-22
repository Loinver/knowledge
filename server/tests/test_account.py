"""账号模块：注册开关、会话令牌、口令维护、用户管理与审计留痕。

重点覆盖三类容易做错的边界：

- **会话**：刷新轮转（旧刷新令牌用一次就废）、登出真吊销、改密只保留当前会话；
- **口令**：强度不足要走 `AUTH.WEAK_PASSWORD` 而不是泛化的 422，重置令牌一次性；
- **越权**：非管理员进不了系统管理，管理员不能把自己降级或禁用。
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from app.api.v1.accounts import router as accounts_router
from app.api.v1.auth import router as auth_router
from app.core.config import get_settings
from app.core.db import Base, get_session
from app.core.errors import install_error_handler
from app.domain import account_service
from app.models.account import AuditLog, AuthToken, User
from app.models.enums import AuditAction, AuditResult, UserRole, UserStatus
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1"
ADMIN_PASSWORD = "admin-password-1"
MEMBER_PASSWORD = "member-password-1"


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """把派生迭代次数压到 1000，否则每条用例都要为 PBKDF2 付几百毫秒。

    清缓存是必须的：`get_settings` 是 lru_cache 单例，别处已经读过一次，
    只设环境变量不生效。
    """
    monkeypatch.setenv("KG_PASSWORD_ITERATIONS", "1000")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/accounts.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(auth_router, prefix=API)
    app.include_router(accounts_router, prefix=API)
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: sessions()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin(sessions: sessionmaker[Session]) -> User:
    with sessions() as session:
        user = account_service.bootstrap_admin(
            session,
            username="root",
            email="root@example.org",
            password=ADMIN_PASSWORD,
            display_name="平台管理员",
        )
        session.commit()
        return user


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, account: str, password: str) -> dict[str, Any]:
    response = client.post(
        f"{API}/auth/login", json={"account": account, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


def make_member(
    sessions: sessionmaker[Session],
    admin: User,
    username: str = "editor",
    role: UserRole = UserRole.EDITOR,
) -> User:
    with sessions() as session:
        actor = session.get(User, admin.id)
        assert actor is not None
        user = account_service.create_user(
            session,
            actor,
            _create_payload(username, role),
            "127.0.0.1",
        )
        session.commit()
        return user


def _create_payload(username: str, role: UserRole) -> Any:
    from app.schemas.account import UserCreate

    return UserCreate(
        username=username,
        email=f"{username}@example.org",
        password=MEMBER_PASSWORD,
        role=role,
        display_name=username.title(),
    )


# ---------------------------------------------------------------------------
# 注册开关
# ---------------------------------------------------------------------------


def test_public_registration_is_closed_by_default(client: TestClient) -> None:
    """默认配置下注册入口关闭，且没有任何账号被建出来。"""
    assert client.get(f"{API}/auth/config").json()["registration_enabled"] is False
    response = client.post(
        f"{API}/auth/register",
        json={
            "username": "newcomer",
            "email": "newcomer@example.org",
            "password": "newcomer-password",
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH.REGISTRATION_CLOSED"


def test_public_registration_creates_viewer_when_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KG_ALLOW_PUBLIC_REGISTRATION", "1")
    get_settings.cache_clear()
    assert client.get(f"{API}/auth/config").json()["registration_enabled"] is True

    response = client.post(
        f"{API}/auth/register",
        json={
            "username": "newcomer",
            "email": "newcomer@example.org",
            "password": "newcomer-password",
        },
    )
    assert response.status_code == 201, response.text
    tokens = response.json()
    me = (
        client.get(f"{API}/auth/me", headers=auth_header(tokens["access_token"]))
    ).json()
    # 注册不能提权：新账号一律只读
    assert me["role"] == "VIEWER"
    assert me["username"] == "newcomer"


def test_bootstrap_admin_refuses_when_accounts_exist(
    sessions: sessionmaker[Session], admin: User
) -> None:
    """种子脚本不能变成第二个提权入口。"""
    from app.core.error_codes import ErrorCode
    from app.core.errors import KGError

    with sessions() as session:
        with pytest.raises(KGError) as caught:
            account_service.bootstrap_admin(
                session,
                username="root2",
                email="root2@example.org",
                password=ADMIN_PASSWORD,
            )
    assert caught.value.code == ErrorCode.ALREADY_EXISTS


# ---------------------------------------------------------------------------
# 登录与会话
# ---------------------------------------------------------------------------


def test_login_accepts_username_or_email_case_insensitively(
    client: TestClient, admin: User
) -> None:
    tokens = login(client, "ROOT", ADMIN_PASSWORD)
    assert tokens["expires_in"] == 3600
    assert tokens["access_token"] != tokens["refresh_token"]

    me = client.get(f"{API}/auth/me", headers=auth_header(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json() == {
        "id": admin.id,
        "username": "root",
        "email": "root@example.org",
        "role": "ADMIN",
        "status": "ACTIVE",
        "display_name": "平台管理员",
        "avatar_url": None,
        "last_login_at": me.json()["last_login_at"],
    }
    assert me.json()["last_login_at"] is not None

    assert login(client, "root@example.org", ADMIN_PASSWORD)["access_token"]


def test_login_does_not_leak_password_hash(client: TestClient, admin: User) -> None:
    """响应里不允许出现口令哈希。"""
    response = client.post(
        f"{API}/auth/login", json={"account": "root", "password": ADMIN_PASSWORD}
    )
    assert "password_hash" not in response.text
    assert "pbkdf2" not in response.text


def test_unknown_account_and_wrong_password_are_indistinguishable(
    client: TestClient, admin: User, sessions: sessionmaker[Session]
) -> None:
    unknown = client.post(
        f"{API}/auth/login", json={"account": "nobody", "password": "whatever-1"}
    )
    wrong = client.post(
        f"{API}/auth/login", json={"account": "root", "password": "wrong-password"}
    )
    for response in (unknown, wrong):
        assert response.status_code == 401
        assert response.json()["code"] == "AUTH.INVALID_CREDENTIALS"
        assert response.json()["data"] is None

    # 失败也留痕：两条 LOGIN/FAILED
    with sessions() as session:
        failed = session.scalars(
            select(AuditLog).where(AuditLog.result == AuditResult.FAILED)
        ).all()
    assert {entry.actor for entry in failed} == {"nobody", "root"}


def test_disabled_account_cannot_login(
    client: TestClient, sessions: sessionmaker[Session], admin: User
) -> None:
    make_member(sessions, admin)
    with sessions() as session:
        member = session.scalar(select(User).where(User.username == "editor"))
        assert member is not None
        account_service.patch_user(
            session,
            session.get(User, admin.id),  # type: ignore[arg-type]
            member.id,
            _user_patch(status=UserStatus.DISABLED),
            "127.0.0.1",
        )
        session.commit()

    response = client.post(
        f"{API}/auth/login", json={"account": "editor", "password": MEMBER_PASSWORD}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH.USER_DISABLED"


def _user_patch(**kwargs: Any) -> Any:
    from app.schemas.account import UserPatch

    return UserPatch(**kwargs)


def test_disabling_account_kills_its_live_session(
    client: TestClient, sessions: sessionmaker[Session], admin: User
) -> None:
    make_member(sessions, admin)
    tokens = login(client, "editor", MEMBER_PASSWORD)
    assert (
        client.get(
            f"{API}/auth/me", headers=auth_header(tokens["access_token"])
        ).status_code
        == 200
    )

    with sessions() as session:
        member = session.scalar(select(User).where(User.username == "editor"))
        assert member is not None
        account_service.patch_user(
            session,
            session.get(User, admin.id),  # type: ignore[arg-type]
            member.id,
            _user_patch(status=UserStatus.DISABLED),
            "127.0.0.1",
        )
        session.commit()

    # 禁用即吊销令牌：在线会话直接作废（401），重新登录才给出 403 的具体原因
    blocked = client.get(f"{API}/auth/me", headers=auth_header(tokens["access_token"]))
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "AUTH.TOKEN_EXPIRED"
    relogin = client.post(
        f"{API}/auth/login", json={"account": "editor", "password": MEMBER_PASSWORD}
    )
    assert relogin.status_code == 403
    assert relogin.json()["code"] == "AUTH.USER_DISABLED"


def test_missing_or_bogus_token_is_rejected(client: TestClient, admin: User) -> None:
    missing = client.get(f"{API}/auth/me")
    assert missing.status_code == 401
    assert missing.json()["code"] == "AUTH.TOKEN_EXPIRED"

    bogus = client.get(f"{API}/auth/me", headers=auth_header("not-a-real-token"))
    assert bogus.status_code == 401
    assert bogus.json()["code"] == "AUTH.TOKEN_EXPIRED"


def test_refresh_rotates_and_replay_is_rejected(
    client: TestClient, admin: User
) -> None:
    first = login(client, "root", ADMIN_PASSWORD)
    rotated = client.post(
        f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (
        client.get(
            f"{API}/auth/me", headers=auth_header(second["access_token"])
        ).status_code
        == 200
    )

    replayed = client.post(
        f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    assert replayed.status_code == 401
    assert replayed.json()["code"] == "AUTH.TOKEN_EXPIRED"


def test_logout_revokes_both_tokens(client: TestClient, admin: User) -> None:
    tokens = login(client, "root", ADMIN_PASSWORD)
    logged_out = client.post(
        f"{API}/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=auth_header(tokens["access_token"]),
    )
    assert logged_out.status_code == 200

    assert (
        client.get(
            f"{API}/auth/me", headers=auth_header(tokens["access_token"])
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )


def test_logout_without_body_still_revokes_access_token(
    client: TestClient, admin: User
) -> None:
    """M1 前端登出时还没带请求体，接口不能因此报 422。"""
    tokens = login(client, "root", ADMIN_PASSWORD)
    assert (
        client.post(
            f"{API}/auth/logout", headers=auth_header(tokens["access_token"])
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"{API}/auth/me", headers=auth_header(tokens["access_token"])
        ).status_code
        == 401
    )


# ---------------------------------------------------------------------------
# 口令维护
# ---------------------------------------------------------------------------


def test_weak_password_is_reported_as_auth_error(
    client: TestClient, sessions: sessionmaker[Session], admin: User
) -> None:
    """强度不足必须是 AUTH.WEAK_PASSWORD，前端才能给出「至少 8 位」的提示。"""
    with sessions() as session:
        actor = session.get(User, admin.id)
        assert actor is not None
        from app.core.error_codes import ErrorCode
        from app.core.errors import KGError
        from app.schemas.account import UserCreate

        with pytest.raises(KGError) as caught:
            account_service.create_user(
                session,
                actor,
                UserCreate(
                    username="shorty",
                    email="shorty@example.org",
                    password="1234567",
                ),
                None,
            )
    assert caught.value.code == ErrorCode.WEAK_PASSWORD
    assert caught.value.params == {"min_length": 8}


def test_change_password_keeps_current_session_and_kills_others(
    client: TestClient, admin: User
) -> None:
    stale = login(client, "root", ADMIN_PASSWORD)
    current = login(client, "root", ADMIN_PASSWORD)

    wrong_old = client.put(
        f"{API}/users/me/password",
        json={"old_password": "not-the-password", "new_password": "brand-new-1"},
        headers=auth_header(current["access_token"]),
    )
    assert wrong_old.status_code == 400
    assert wrong_old.json()["code"] == "AUTH.OLD_PASSWORD_INVALID"

    changed = client.put(
        f"{API}/users/me/password",
        json={"old_password": ADMIN_PASSWORD, "new_password": "brand-new-1"},
        headers=auth_header(current["access_token"]),
    )
    assert changed.status_code == 200, changed.text

    # 当前会话保留，其他会话失效
    assert (
        client.get(
            f"{API}/auth/me", headers=auth_header(current["access_token"])
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"{API}/auth/me", headers=auth_header(stale["access_token"])
        ).status_code
        == 401
    )

    # 旧口令失效，新口令可用
    assert (
        client.post(
            f"{API}/auth/login", json={"account": "root", "password": ADMIN_PASSWORD}
        ).status_code
        == 401
    )
    assert login(client, "root", "brand-new-1")["access_token"]


def test_profile_update_only_touches_sent_fields(
    client: TestClient, admin: User
) -> None:
    tokens = login(client, "root", ADMIN_PASSWORD)
    updated = client.patch(
        f"{API}/users/me/profile",
        json={"display_name": "改名了"},
        headers=auth_header(tokens["access_token"]),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "改名了"
    assert updated.json()["avatar_url"] is None

    fetched = client.get(
        f"{API}/users/me/profile", headers=auth_header(tokens["access_token"])
    )
    assert fetched.json()["display_name"] == "改名了"


# ---------------------------------------------------------------------------
# 忘记与重置口令
# ---------------------------------------------------------------------------


def test_forgot_password_does_not_reveal_account_existence(
    client: TestClient, admin: User
) -> None:
    unknown = client.post(
        f"{API}/auth/forgot-password", json={"email": "nobody@example.org"}
    )
    assert unknown.status_code == 200
    assert unknown.json() == {"reset_token": None, "expires_in": 0}

    known = client.post(
        f"{API}/auth/forgot-password", json={"email": "root@example.org"}
    )
    assert known.status_code == 200
    assert known.json()["reset_token"]
    assert known.json()["expires_in"] == 3600


def test_reset_password_consumes_token_and_revokes_sessions(
    client: TestClient, admin: User, sessions: sessionmaker[Session]
) -> None:
    live = login(client, "root", ADMIN_PASSWORD)
    token = client.post(
        f"{API}/auth/forgot-password", json={"email": "root@example.org"}
    ).json()["reset_token"]

    reset = client.post(
        f"{API}/auth/reset-password",
        json={"token": token, "password": "reset-password-1"},
    )
    assert reset.status_code == 200, reset.text

    # 令牌一次性
    replay = client.post(
        f"{API}/auth/reset-password",
        json={"token": token, "password": "another-password-1"},
    )
    assert replay.status_code == 400
    assert replay.json()["code"] == "AUTH.RESET_TOKEN_INVALID"

    # 重置即踢下线，新口令可用
    assert (
        client.get(
            f"{API}/auth/me", headers=auth_header(live["access_token"])
        ).status_code
        == 401
    )
    assert login(client, "root", "reset-password-1")["access_token"]

    with sessions() as session:
        entry = session.scalar(
            select(AuditLog).where(AuditLog.action == AuditAction.PASSWORD_RESET)
        )
    assert entry is not None and entry.result == AuditResult.OK


def test_reset_token_is_hidden_when_not_exposed(
    client: TestClient, admin: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """生产把令牌交给邮件，响应里只能是 null。"""
    monkeypatch.setenv("KG_EXPOSE_RESET_TOKEN", "0")
    get_settings.cache_clear()
    response = client.post(
        f"{API}/auth/forgot-password", json={"email": "root@example.org"}
    )
    assert response.status_code == 200
    assert response.json() == {"reset_token": None, "expires_in": 0}


def test_weak_password_on_reset_is_rejected_before_consuming_token(
    client: TestClient, admin: User
) -> None:
    token = client.post(
        f"{API}/auth/forgot-password", json={"email": "root@example.org"}
    ).json()["reset_token"]
    weak = client.post(
        f"{API}/auth/reset-password", json={"token": token, "password": "short"}
    )
    assert weak.status_code == 400
    assert weak.json()["code"] == "AUTH.WEAK_PASSWORD"
    # 令牌没被消耗，仍可用
    assert (
        client.post(
            f"{API}/auth/reset-password",
            json={"token": token, "password": "long-enough-1"},
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# 系统管理
# ---------------------------------------------------------------------------


def test_duplicate_username_and_email_conflict(client: TestClient, admin: User) -> None:
    tokens = login(client, "root", ADMIN_PASSWORD)
    first = client.post(
        f"{API}/users",
        json={
            "username": "editor",
            "email": "editor@example.org",
            "password": MEMBER_PASSWORD,
            "role": "EDITOR",
        },
        headers=auth_header(tokens["access_token"]),
    )
    assert first.status_code == 201, first.text
    assert first.json()["role"] == "EDITOR"
    assert first.json()["status"] == "ACTIVE"

    same_username = client.post(
        f"{API}/users",
        json={
            "username": "Editor",
            "email": "other@example.org",
            "password": MEMBER_PASSWORD,
        },
        headers=auth_header(tokens["access_token"]),
    )
    assert same_username.status_code == 409
    assert same_username.json()["code"] == "AUTH.USERNAME_TAKEN"

    same_email = client.post(
        f"{API}/users",
        json={
            "username": "other",
            "email": "editor@example.org",
            "password": MEMBER_PASSWORD,
        },
        headers=auth_header(tokens["access_token"]),
    )
    assert same_email.status_code == 409
    assert same_email.json()["code"] == "AUTH.EMAIL_TAKEN"


def test_non_admin_is_forbidden_from_system_endpoints(
    client: TestClient, sessions: sessionmaker[Session], admin: User
) -> None:
    make_member(sessions, admin)
    tokens = login(client, "editor", MEMBER_PASSWORD)
    headers = auth_header(tokens["access_token"])

    for method, path in (
        ("get", f"{API}/users"),
        ("get", f"{API}/roles"),
        ("get", f"{API}/audit-logs"),
    ):
        response = getattr(client, method)(path, headers=headers)
        assert response.status_code == 403, path
        assert response.json()["code"] == "AUTH.FORBIDDEN"

    # 编辑者改自己的资料仍然允许
    assert (
        client.patch(
            f"{API}/users/me/profile", json={"display_name": "编辑"}, headers=headers
        ).status_code
        == 200
    )


def test_user_list_paging_search_and_filters(
    client: TestClient, sessions: sessionmaker[Session], admin: User
) -> None:
    make_member(sessions, admin, "editor")
    make_member(sessions, admin, "auditor", UserRole.VIEWER)
    headers = auth_header(login(client, "root", ADMIN_PASSWORD)["access_token"])

    page = client.get(f"{API}/users", params={"page_size": 2}, headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2

    searched = client.get(f"{API}/users", params={"q": "audit"}, headers=headers)
    assert [item["username"] for item in searched.json()["items"]] == ["auditor"]

    by_role = client.get(f"{API}/users", params={"role": "VIEWER"}, headers=headers)
    assert [item["username"] for item in by_role.json()["items"]] == ["auditor"]

    by_status = client.get(
        f"{API}/users", params={"status": "DISABLED"}, headers=headers
    )
    assert by_status.json()["total"] == 0


def test_admin_cannot_lock_itself_out(client: TestClient, admin: User) -> None:
    """最后一个管理员自锁后没有任何界面入口能恢复，必须挡住。"""
    headers = auth_header(login(client, "root", ADMIN_PASSWORD)["access_token"])
    demote = client.patch(
        f"{API}/users/{admin.id}", json={"role": "VIEWER"}, headers=headers
    )
    assert demote.status_code == 403
    assert demote.json()["code"] == "AUTH.FORBIDDEN"

    disable = client.patch(
        f"{API}/users/{admin.id}", json={"status": "DISABLED"}, headers=headers
    )
    assert disable.status_code == 403

    # 自己的角色与状态都没变
    me = client.get(f"{API}/auth/me", headers=headers).json()
    assert me["role"] == "ADMIN" and me["status"] == "ACTIVE"


def test_admin_can_change_other_role_and_status(
    client: TestClient, sessions: sessionmaker[Session], admin: User
) -> None:
    member = make_member(sessions, admin, "editor")
    headers = auth_header(login(client, "root", ADMIN_PASSWORD)["access_token"])

    promoted = client.patch(
        f"{API}/users/{member.id}", json={"role": "ADMIN"}, headers=headers
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["role"] == "ADMIN"

    missing = client.patch(
        f"{API}/users/does-not-exist", json={"role": "VIEWER"}, headers=headers
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "KG.RESOURCE_NOT_FOUND"


def test_roles_report_member_counts(
    client: TestClient, sessions: sessionmaker[Session], admin: User
) -> None:
    make_member(sessions, admin, "editor")
    headers = auth_header(login(client, "root", ADMIN_PASSWORD)["access_token"])

    roles = client.get(f"{API}/roles", headers=headers)
    assert roles.status_code == 200
    # 角色名与说明是界面文案，后端只给码和人数
    assert roles.json() == [
        {"code": "ADMIN", "member_count": 1},
        {"code": "EDITOR", "member_count": 1},
        {"code": "VIEWER", "member_count": 0},
    ]


def test_audit_logs_are_paged_newest_first_and_filterable(
    client: TestClient, sessions: sessionmaker[Session], admin: User
) -> None:
    login(client, "root", ADMIN_PASSWORD)
    login(client, "root", ADMIN_PASSWORD)
    headers = auth_header(login(client, "root", ADMIN_PASSWORD)["access_token"])

    page = client.get(f"{API}/audit-logs", params={"page_size": 2}, headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert [item["action"] for item in page.json()["items"]] == ["LOGIN", "LOGIN"]

    filtered = client.get(
        f"{API}/audit-logs", params={"action": "LOGOUT"}, headers=headers
    )
    assert filtered.json()["total"] == 0

    by_actor = client.get(f"{API}/audit-logs", params={"q": "root"}, headers=headers)
    assert by_actor.json()["total"] == 3
    # 时间带 UTC 标记，前端 new Date() 才不会按本地时区误读
    assert by_actor.json()["items"][0]["created_at"].endswith(("Z", "+00:00"))


def test_invalid_query_enum_is_rejected(client: TestClient, admin: User) -> None:
    headers = auth_header(login(client, "root", ADMIN_PASSWORD)["access_token"])
    response = client.get(f"{API}/users", params={"role": "SUPERUSER"}, headers=headers)
    assert response.status_code == 422
    assert response.json()["code"] == "KG.INVALID_REQUEST"


def test_username_and_email_format_are_validated(
    client: TestClient, admin: User
) -> None:
    headers = auth_header(login(client, "root", ADMIN_PASSWORD)["access_token"])
    bad_username = client.post(
        f"{API}/users",
        json={
            "username": "ab",
            "email": "ok@example.org",
            "password": MEMBER_PASSWORD,
        },
        headers=headers,
    )
    assert bad_username.status_code == 422

    bad_email = client.post(
        f"{API}/users",
        json={
            "username": "goodname",
            "email": "not-an-email",
            "password": MEMBER_PASSWORD,
        },
        headers=headers,
    )
    assert bad_email.status_code == 422


# ---------------------------------------------------------------------------
# 迁移
# ---------------------------------------------------------------------------


def test_account_migration_upgrade_downgrade_replays(tmp_path: Path) -> None:
    """0007 须能在已有部署上升级、降级并重放，且不触碰既有数据。"""
    database_url = f"sqlite:///{tmp_path}/account-migration.db"
    environment = {**os.environ, "KG_DATABASE_URL": database_url}

    def migrate(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "head")
    engine = create_engine(database_url)
    tables = inspect(engine).get_table_names()
    assert {
        "app_user",
        "auth_token",
        "password_reset_token",
        "audit_log",
    } <= set(tables)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO namespace (prefix, iri, protected) VALUES (:p, :i, 0)"),
            {"p": "example", "i": "https://example.org/"},
        )

    migrate("downgrade", "0006_prop_constraints")
    remaining = inspect(engine).get_table_names()
    assert "app_user" not in remaining
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT prefix FROM namespace")) == "example"

    migrate("upgrade", "head")
    assert "app_user" in inspect(engine).get_table_names()
    with Session(engine) as session:
        account_service.bootstrap_admin(
            session,
            username="root",
            email="root@example.org",
            password=ADMIN_PASSWORD,
        )
        session.commit()
        assert session.scalar(select(User.username)) == "root"
        assert session.scalar(select(AuthToken.id)) is None
    engine.dispose()
