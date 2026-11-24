"""数据源连接管理集成测试（H-20）。"""

from __future__ import annotations

import base64
import hashlib

import pytest
from app.core.config import get_settings
from app.core.crypto import decrypt, encrypt
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.source_service import (
    create_datasource,
    delete_datasource,
    get_datasource,
    get_display_params,
    reencrypt_datasources,
)
from app.domain.source_service import (
    test_connection as _test_connection,
)
from app.models.data_access import Datasource
from app.schemas.datasource import DatasourceCreate, TestConnectionRequest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def session(tmp_path):
    url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = sf()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


def test_create_datasource_encrypts_credential(session):
    """凭据加密后存，浏览器只拿脱敏参数（A15）。"""
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="hr-db",
            kind="sqlite",
            params={"database": "/tmp/hr.db"},
            credential="secret123",
        ),
    )
    session.commit()
    assert ds.credential_cipher is not None
    assert ds.credential_cipher.startswith("aesgcm:v1:")
    assert "secret123" not in ds.credential_cipher
    assert decrypt(ds.credential_cipher) == "secret123"
    display = get_display_params(ds)
    assert "password" not in display


def test_create_duplicate_rejected(session):
    create_datasource(
        session,
        DatasourceCreate(
            name="hr-db",
            kind="sqlite",
            params={"database": "/tmp/hr.db"},
        ),
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        create_datasource(
            session,
            DatasourceCreate(
                name="hr-db",
                kind="sqlite",
                params={"database": "/tmp/hr2.db"},
            ),
        )
    assert exc.value.code == ErrorCode.ALREADY_EXISTS


def test_test_connection_sqlite_success():
    """SQLite 连接测试成功。"""
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    result = _test_connection("sqlite", {"database": path})
    os.unlink(path)
    assert result["ok"] is True
    assert result["table_count"] is not None
    assert result["table_count"] > 0


def test_test_connection_failure():
    """不存在的数据库连接失败。"""
    result = _test_connection("sqlite", {"database": "/nonexistent/path.db"})
    assert result["ok"] is False
    assert result["table_count"] is None


def test_test_connection_unsupported_kind():
    result = _test_connection("oracle", {})
    assert result["ok"] is False


def test_get_nonexistent_raises(session):
    with pytest.raises(KGError) as exc:
        get_datasource(session, 9999)
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_delete_datasource(session):
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="temp-db",
            kind="sqlite",
            params={"database": "/tmp/temp.db"},
        ),
    )
    session.commit()
    delete_datasource(session, ds.id)
    session.commit()
    with pytest.raises(KGError):
        get_datasource(session, ds.id)


def test_credential_never_in_display(session):
    """凭据不出现在浏览器可见的参数里（A15）。"""
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="secure-db",
            kind="sqlite",
            params={"host": "localhost", "user": "admin"},
            credential="topsecret",
        ),
    )
    session.commit()
    display = get_display_params(ds)
    assert "topsecret" not in str(display)
    assert display["host"] == "localhost"


@pytest.mark.parametrize("schema", [DatasourceCreate, TestConnectionRequest])
def test_new_requests_reject_secrets_inside_params(schema):
    payload = {
        "kind": "sqlite",
        "params": {"database": "/tmp/hr.db", "PaSsWoRd": "plain-secret"},
    }
    if schema is DatasourceCreate:
        payload["name"] = "unsafe"
    with pytest.raises(ValidationError, match="credential field"):
        schema.model_validate(payload)


def test_legacy_secrets_migrate_in_one_transaction(session):
    old_key = hashlib.sha256(get_settings().crypto_key.encode()).digest()
    secret = b"legacy-secret"
    legacy = base64.b64encode(
        bytes(value ^ old_key[i % len(old_key)] for i, value in enumerate(secret))
    ).decode()
    ds = Datasource(
        name="legacy",
        kind="sqlite",
        params={"database": "/tmp/hr.db", "password": secret.decode()},
        credential_cipher=legacy,
    )
    session.add(ds)
    session.commit()

    assert get_display_params(ds)["password"] == "***"
    assert reencrypt_datasources(session) == 1
    session.commit()
    assert ds.params == {"database": "/tmp/hr.db"}
    assert ds.credential_cipher.startswith("aesgcm:v1:")
    assert decrypt(ds.credential_cipher) == secret.decode()
    assert reencrypt_datasources(session) == 0


def test_empty_legacy_secret_survives_key_rotation(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    ds = Datasource(
        name="empty-secret",
        kind="sqlite",
        params={"database": "/tmp/hr.db", "password": ""},
    )
    session.add(ds)
    session.commit()
    assert reencrypt_datasources(session) == 1
    session.commit()
    assert ds.params == {"database": "/tmp/hr.db"}
    assert decrypt(ds.credential_cipher) == ""
    previous_key = get_settings().crypto_key
    previous_cipher = ds.credential_cipher
    monkeypatch.setattr(get_settings(), "crypto_key", "test-rotated-key")
    assert reencrypt_datasources(session, previous_key=previous_key) == 1
    session.commit()
    assert ds.credential_cipher != previous_cipher
    assert decrypt(ds.credential_cipher) == ""


def test_conflicting_legacy_secrets_abort_migration(session):
    ds = Datasource(
        name="conflict",
        kind="sqlite",
        params={"database": "/tmp/hr.db", "password": "different"},
        credential_cipher=encrypt("original"),
    )
    session.add(ds)
    session.commit()
    with pytest.raises(ValueError, match="conflicting credentials"):
        reencrypt_datasources(session)
    session.rollback()
    session.refresh(ds)
    assert ds.params["password"] == "different"


def test_authenticated_ciphertext_is_randomized_and_tamper_detected():
    first = encrypt("my-password-123")
    second = encrypt("my-password-123")
    assert first != second
    payload = bytearray(base64.b64decode(first.split(":", 2)[2]))
    payload[-1] ^= 1
    tampered = "aesgcm:v1:" + base64.b64encode(payload).decode()
    with pytest.raises(ValueError, match="Invalid credential ciphertext"):
        decrypt(tampered)


def test_encrypt_decrypt_roundtrip():
    """凭据加解密往返。"""
    plaintext = "my-password-123"
    cipher = encrypt(plaintext)
    assert cipher != plaintext
    assert decrypt(cipher) == plaintext


def test_update_datasource_renames_and_reencrypts(session):
    """PUT 更新：改名、换参数、换凭据（重新加密），凭据不出后端。"""
    from app.domain.source_service import update_datasource
    from app.schemas.datasource import DatasourceUpdate

    ds = create_datasource(
        session,
        DatasourceCreate(
            name="hr-db",
            kind="sqlite",
            params={"database": "/tmp/hr.db"},
            credential="secret123",
        ),
    )
    session.commit()

    updated = update_datasource(
        session,
        ds.id,
        DatasourceUpdate(name="finance-db", credential="new-secret"),
    )
    session.commit()
    assert updated.name == "finance-db"
    assert decrypt(updated.credential_cipher) == "new-secret"


def test_update_datasource_duplicate_name_rejected(session):
    from app.domain.source_service import update_datasource
    from app.schemas.datasource import DatasourceUpdate

    create_datasource(
        session,
        DatasourceCreate(name="hr-db", kind="sqlite", params={"database": "/tmp/a.db"}),
    )
    other = create_datasource(
        session,
        DatasourceCreate(
            name="fin-db", kind="sqlite", params={"database": "/tmp/b.db"}
        ),
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        update_datasource(session, other.id, DatasourceUpdate(name="hr-db"))
    assert exc.value.code == ErrorCode.ALREADY_EXISTS


def test_update_datasource_resets_status(session):
    """换参数/换凭据后旧连接状态不可信，重置为 DISCONNECTED。"""
    from app.domain.source_service import update_datasource
    from app.schemas.datasource import DatasourceUpdate

    ds = create_datasource(
        session,
        DatasourceCreate(
            name="hr-db", kind="sqlite", params={"database": "/tmp/hr.db"}
        ),
    )
    ds.status = "CONNECTED"
    session.commit()

    updated = update_datasource(
        session, ds.id, DatasourceUpdate(params={"database": "/tmp/other.db"})
    )
    session.commit()
    assert updated.status == "DISCONNECTED"


def test_stored_test_connection_persists_status(session, tmp_path):
    """测试连接结果落库：ok → CONNECTED，失败 → DISCONNECTED。"""
    from app.domain.source_service import test_stored_connection

    db_file = tmp_path / "hr.db"
    db_file.write_text("")
    ds = create_datasource(
        session,
        DatasourceCreate(
            name="hr-db", kind="sqlite", params={"database": str(db_file)}
        ),
    )
    session.commit()

    result = test_stored_connection(session, ds.id)
    session.commit()
    assert result["ok"] is True
    assert result["status"] == "CONNECTED"
    assert get_datasource(session, ds.id).status == "CONNECTED"

    bad = create_datasource(
        session,
        DatasourceCreate(
            name="ghost", kind="sqlite", params={"database": "/nonexistent/x.db"}
        ),
    )
    session.commit()
    failed = test_stored_connection(session, bad.id)
    session.commit()
    assert failed["ok"] is False
    assert failed["status"] == "DISCONNECTED"
