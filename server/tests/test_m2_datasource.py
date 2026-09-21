"""数据源连接管理集成测试（H-20）。"""

from __future__ import annotations

import pytest
from app.core.crypto import decrypt, encrypt
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.source_service import (
    create_datasource,
    delete_datasource,
    get_datasource,
    get_display_params,
)
from app.domain.source_service import (
    test_connection as _test_connection,
)
from app.schemas.datasource import DatasourceCreate
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
            params={"database": "/tmp/hr.db", "password": "secret123"},
            credential="secret123",
        ),
    )
    session.commit()
    assert ds.credential_cipher is not None
    assert "secret123" not in ds.credential_cipher
    assert decrypt(ds.credential_cipher) == "secret123"
    display = get_display_params(ds)
    assert display["password"] == "***"


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
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


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
            params={"host": "localhost", "password": "topsecret", "user": "admin"},
            credential="topsecret",
        ),
    )
    session.commit()
    display = get_display_params(ds)
    assert "topsecret" not in str(display)
    assert display["password"] == "***"
    assert display["host"] == "localhost"


def test_encrypt_decrypt_roundtrip():
    """凭据加解密往返。"""
    plaintext = "my-password-123"
    cipher = encrypt(plaintext)
    assert cipher != plaintext
    assert decrypt(cipher) == plaintext
