"""M0 后端集成测试。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import register_namespace, scan_rename_impact
from app.domain.status_service import check_revision, publish_resource
from app.main import app
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import ModelResource, ResourceRef
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def session(tmp_path):
    """每个测试用独立 SQLite 库。"""
    url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = session_factory()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


def _make_namespace(session) -> None:
    ns = register_namespace(session, "kg", "https://example.org/kg#", protected=False)
    return ns


def _make_resource(session, ns, name="Employee") -> ModelResource:
    res = ModelResource(
        kind=ResourceKind.ENTITY,
        name=name,
        iri=f"https://example.org/kg#{name}",
        namespace_id=ns.id,
        status=ResourceStatus.DRAFT,
    )
    session.add(res)
    session.flush()
    return res


def test_publish_creates_immutable_revision(session):
    """发布即冻结：resource_revision 只增不改。"""
    ns = _make_namespace(session)
    res = _make_resource(session, ns)
    rev = publish_resource(session, res)
    session.commit()
    assert rev.revision == 1
    assert res.current_revision == 1
    assert res.status == ResourceStatus.PUBLISHED


def test_already_published_cannot_republish(session):
    """已发布的资源不能直接再发，需先改草稿。"""
    ns = _make_namespace(session)
    res = _make_resource(session, ns)
    publish_resource(session, res)
    session.commit()
    with pytest.raises(KGError) as exc:
        publish_resource(session, res)
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_revision_optimistic_lock(session):
    """乐观锁：If-Match 不匹配返回 REVISION_CONFLICT。"""
    ns = _make_namespace(session)
    res = _make_resource(session, ns)
    # 资源 current_revision=0，传入 if_match=5 应冲突
    with pytest.raises(KGError) as exc:
        check_revision(res, if_match=5)
    assert exc.value.code == ErrorCode.REVISION_CONFLICT
    assert exc.value.params["expected"] == 0
    assert exc.value.params["actual"] == 5


def test_check_revision_requires_if_match(session):
    """写接口必须带 If-Match。"""
    ns = _make_namespace(session)
    res = _make_resource(session, ns)
    with pytest.raises(KGError) as exc:
        check_revision(res, if_match=None)
    assert exc.value.code == ErrorCode.INVALID_REQUEST


def test_rename_impact_scan(session):
    """更名影响面扫描：返回引用方列表。"""
    ns = _make_namespace(session)
    res = _make_resource(session, ns)
    other = _make_resource(session, ns, name="Department")
    # other 引用 res
    session.add(
        ResourceRef(source_id=other.id, target_id=res.id, role="relation_endpoint")
    )
    session.commit()
    refs = scan_rename_impact(session, res.id)
    assert len(refs) == 1
    assert refs[0].source_id == other.id
    assert refs[0].role == "relation_endpoint"


def test_protected_namespace_cannot_delete(session):
    """protected 命名空间不可删。"""
    from app.domain.iri_service import delete_namespace

    ns = register_namespace(session, "std", "https://example.org/std#", protected=True)
    session.commit()
    with pytest.raises(KGError) as exc:
        delete_namespace(session, ns.id)
    assert exc.value.code == ErrorCode.PROTECTED_NAMESPACE


def test_namespace_duplicate_rejected(session):
    """重复 prefix/iri 不可注册。"""
    _make_namespace(session)
    with pytest.raises(KGError) as exc:
        register_namespace(session, "kg", "https://other.org/#")
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_invalid_name_rejected(session):
    """非法机读名被拒。"""
    from app.domain.iri_service import validate_name

    with pytest.raises(KGError) as exc:
        validate_name("employee_name")
    assert exc.value.code == ErrorCode.INVALID_NAME


def test_health_endpoint():
    """/health 返回 ok。"""
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
