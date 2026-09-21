"""业务域管理集成测试（H-10）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.domain_service import (
    add_member,
    check_publish,
    create_domain,
    list_members,
    publish_domain,
    update_domain,
)
from app.domain.iri_service import register_namespace
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.schemas.domain import DomainCreate, DomainMemberAdd, DomainUpdate
from app.schemas.type import EntityTypeCreate
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


@pytest.fixture()
def ns(session):
    return register_namespace(session, "kg", "https://example.org/kg#")


@pytest.fixture()
def published_type(session, ns):
    """已发布的实体类型。"""
    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工", "en-US": "Employee"},
        ),
    )
    publish_resource(session, res)
    session.commit()
    return res


def _make_domain(session, name="HR"):
    return create_domain(
        session,
        DomainCreate(
            name=name,
            iri=f"https://example.org/dom#{name}",
            label_i18n={"zh-CN": "人力资源", "en-US": "Human Resources"},
        ),
    )


def test_create_domain(session):
    domain = _make_domain(session)
    session.commit()
    assert domain.name == "HR"
    assert domain.status.value == "DRAFT"


def test_create_duplicate_rejected(session):
    _make_domain(session)
    with pytest.raises(KGError) as exc:
        _make_domain(session)
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_add_member(session, published_type):
    domain = _make_domain(session)
    session.commit()
    add_member(
        session,
        domain.id,
        DomainMemberAdd(resource_id=published_type.id),
    )
    session.commit()
    members = list_members(session, domain.id)
    assert len(members) == 1
    assert members[0].resource_id == published_type.id
    assert members[0].as_ref is False


def test_add_duplicate_member_rejected(session, published_type):
    domain = _make_domain(session)
    add_member(session, domain.id, DomainMemberAdd(resource_id=published_type.id))
    with pytest.raises(KGError) as exc:
        add_member(session, domain.id, DomainMemberAdd(resource_id=published_type.id))
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_add_nonexistent_member_rejected(session):
    domain = _make_domain(session)
    with pytest.raises(KGError) as exc:
        add_member(session, domain.id, DomainMemberAdd(resource_id=9999))
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_publish_check_blocks_unpublished(session, ns):
    """成员未发布时，发布检查不通过。"""
    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工"},
        ),
    )
    domain = _make_domain(session)
    add_member(session, domain.id, DomainMemberAdd(resource_id=res.id))
    session.commit()
    check = check_publish(session, domain)
    assert check.versions_available is False
    assert check.can_publish is False


def test_publish_check_passes_with_published(session, published_type):
    domain = _make_domain(session)
    add_member(session, domain.id, DomainMemberAdd(resource_id=published_type.id))
    session.commit()
    check = check_publish(session, domain)
    assert check.can_publish is True


def test_publish_domain(session, published_type):
    domain = _make_domain(session)
    add_member(session, domain.id, DomainMemberAdd(resource_id=published_type.id))
    session.commit()
    revision = publish_domain(session, domain)
    session.commit()
    assert revision == 1
    assert domain.current_revision == 1
    assert domain.status.value == "PUBLISHED"


def test_publish_blocked_when_unpublished(session, ns):
    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工"},
        ),
    )
    domain = _make_domain(session)
    add_member(session, domain.id, DomainMemberAdd(resource_id=res.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        publish_domain(session, domain)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_update_domain_if_match(session):
    domain = _make_domain(session)
    session.commit()
    update_domain(
        session,
        domain,
        DomainUpdate(label_i18n={"zh-CN": "新名", "en-US": "NewName"}, if_match=0),
    )
    session.commit()
    assert domain.label_i18n["zh-CN"] == "新名"


def test_update_revision_conflict(session):
    domain = _make_domain(session)
    session.commit()
    with pytest.raises(KGError) as exc:
        update_domain(
            session,
            domain,
            DomainUpdate(label_i18n={"zh-CN": "x"}, if_match=99),
        )
    assert exc.value.code == ErrorCode.REVISION_CONFLICT


def test_cross_domain_ref(session, published_type):
    """跨域引用：as_ref=True。"""
    domain_a = _make_domain(session, name="HR")
    domain_b = _make_domain(session, name="Finance")
    session.commit()
    add_member(
        session,
        domain_b.id,
        DomainMemberAdd(
            resource_id=published_type.id,
            as_ref=True,
            owner_domain_id=domain_a.id,
        ),
    )
    session.commit()
    members = list_members(session, domain_b.id)
    assert members[0].as_ref is True
    assert members[0].owner_domain_id == domain_a.id
