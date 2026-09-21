"""实体类型库集成测试（H-11）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.status_service import publish_resource
from app.domain.type_service import (
    create_entity_type,
    get_data_props,
    get_entity_type,
    get_parent_ids,
    list_entity_types,
    update_entity_type,
)
from app.models.enums import ResourceKind, ResourceStatus
from app.schemas.type import (
    DataTypePropCreate,
    EntityTypeCreate,
    EntityTypeUpdate,
)
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


def _make_type(session, ns, name="Employee"):
    return create_entity_type(
        session,
        EntityTypeCreate(
            name=name,
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工", "en-US": "Employee"},
        ),
    )


def test_create_entity_type(session, ns):
    res = _make_type(session, ns)
    session.commit()
    assert res.kind == ResourceKind.ENTITY
    assert res.name == "Employee"
    assert res.iri == "https://example.org/kg#Employee"
    assert res.status == ResourceStatus.DRAFT
    assert res.label_i18n["zh-CN"] == "员工"
    assert res.label_i18n["en-US"] == "Employee"


def test_create_duplicate_name_rejected(session, ns):
    _make_type(session, ns)
    with pytest.raises(KGError) as exc:
        _make_type(session, ns)
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_create_invalid_name_rejected(session, ns):
    with pytest.raises(KGError) as exc:
        create_entity_type(
            session,
            EntityTypeCreate(
                name="employee_name",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "x"},
            ),
        )
    assert exc.value.code == ErrorCode.INVALID_NAME


def test_update_with_if_match(session, ns):
    res = _make_type(session, ns)
    session.commit()
    updated = update_entity_type(
        session,
        res,
        EntityTypeUpdate(label_i18n={"zh-CN": "新名", "en-US": "NewName"}, if_match=0),
    )
    assert updated.label_i18n["zh-CN"] == "新名"


def test_update_revision_conflict(session, ns):
    res = _make_type(session, ns)
    session.commit()
    with pytest.raises(KGError) as exc:
        update_entity_type(
            session,
            res,
            EntityTypeUpdate(label_i18n={"zh-CN": "x"}, if_match=99),
        )
    assert exc.value.code == ErrorCode.REVISION_CONFLICT


def test_type_hierarchy(session, ns):
    parent = _make_type(session, ns, name="Person")
    child = _make_type(session, ns, name="Employee")
    session.commit()
    update_entity_type(
        session,
        child,
        EntityTypeUpdate(parent_ids=[parent.id], if_match=0),
    )
    session.commit()
    assert get_parent_ids(session, child) == [parent.id]


def test_publish_freezes_revision(session, ns):
    res = _make_type(session, ns)
    session.commit()
    rev = publish_resource(session, res)
    session.commit()
    assert rev.revision == 1
    assert res.current_revision == 1
    assert res.status == ResourceStatus.PUBLISHED


def test_list_and_search(session, ns):
    _make_type(session, ns, name="Employee")
    _make_type(session, ns, name="Department")
    session.commit()
    _items, total = list_entity_types(session, "")
    assert total == 2
    items_q, total_q = list_entity_types(session, "Emp")
    assert total_q == 1
    assert items_q[0].name == "Employee"


def test_data_props(session, ns):
    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工"},
            data_props=[
                DataTypePropCreate(
                    name="code",
                    datatype="string",
                    label_i18n={"zh-CN": "工号"},
                ),
            ],
        ),
    )
    session.commit()
    props = get_data_props(session, res)
    assert len(props) == 1
    assert props[0].kind == ResourceKind.DATATYPE_PROP
    assert props[0].name == "Employee.code"


def test_get_nonexistent_raises(session):
    with pytest.raises(KGError) as exc:
        get_entity_type(session, 9999)
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND
