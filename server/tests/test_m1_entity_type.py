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


def test_type_hierarchy_rejects_direct_cycle(session, ns):
    """A→B 之后把 A 的父设为 B，必须拒绝，且不得留下任何边。"""
    a = _make_type(session, ns, name="A")
    b = _make_type(session, ns, name="B")
    session.commit()
    update_entity_type(session, b, EntityTypeUpdate(parent_ids=[a.id], if_match=0))
    session.commit()

    with pytest.raises(KGError) as exc:
        update_entity_type(session, a, EntityTypeUpdate(parent_ids=[b.id], if_match=0))
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION
    assert exc.value.params["reason"] == "hierarchy_cycle"
    session.rollback()

    assert get_parent_ids(session, a) == []


def test_type_hierarchy_rejects_indirect_cycle(session, ns):
    """A→B→C 之后把 A 的父设为 C，间接环同样必须拒绝。"""
    a = _make_type(session, ns, name="A")
    b = _make_type(session, ns, name="B")
    c = _make_type(session, ns, name="C")
    session.commit()
    update_entity_type(session, b, EntityTypeUpdate(parent_ids=[a.id], if_match=0))
    update_entity_type(session, c, EntityTypeUpdate(parent_ids=[b.id], if_match=0))
    session.commit()

    with pytest.raises(KGError) as exc:
        update_entity_type(session, a, EntityTypeUpdate(parent_ids=[c.id], if_match=0))
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION
    assert exc.value.params["reason"] == "hierarchy_cycle"


def test_type_hierarchy_still_skips_self_parent(session, ns):
    """自父沿用原有语义：静默跳过，不报环。"""
    a = _make_type(session, ns, name="A")
    session.commit()
    update_entity_type(session, a, EntityTypeUpdate(parent_ids=[a.id], if_match=0))
    session.commit()
    assert get_parent_ids(session, a) == []


def test_type_hierarchy_allows_reparent_after_removing_edge(session, ns):
    """解除旧边后可以重新挂到原祖先之上，说明判定的是"本次设置之后"的图。"""
    a = _make_type(session, ns, name="A")
    b = _make_type(session, ns, name="B")
    session.commit()
    update_entity_type(session, b, EntityTypeUpdate(parent_ids=[a.id], if_match=0))
    session.commit()

    # B 先解除父边，再把 A 挂到 B 之下：此时不存在环，应当允许。
    update_entity_type(
        session, b, EntityTypeUpdate(parent_ids=[], if_match=0, edit_revision=1)
    )
    session.commit()
    update_entity_type(session, a, EntityTypeUpdate(parent_ids=[b.id], if_match=0))
    session.commit()
    assert get_parent_ids(session, a) == [b.id]
    assert get_parent_ids(session, b) == []


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


def test_rename_draft_rebuilds_iri_and_child_props(session, ns):
    """B-6：草稿态改名重建自身 IRI 与子数据属性 IRI。"""
    from app.domain.iri_service import rename_resource

    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工"},
            data_props=[
                DataTypePropCreate(
                    name="code", datatype="string", label_i18n={"zh-CN": "工号"}
                ),
            ],
        ),
    )
    session.commit()
    old_iri = res.iri
    old_prop_iri = get_data_props(session, res)[0].iri
    assert old_prop_iri == f"{old_iri}/code"

    rename_resource(session, res.id, "Staff")
    session.commit()
    assert res.name == "Staff"
    assert res.iri == "https://example.org/kg#Staff"
    # 子数据属性 IRI 随之重建
    prop = get_data_props(session, res)[0]
    assert prop.name == "Staff.code"
    assert prop.iri == "https://example.org/kg#Staff/code"


def test_rename_rejected_for_published_resource(session, ns):
    """B-6：已发布资源的 IRI 被版本冻结，拒绝改名。"""
    from app.domain.iri_service import rename_resource

    res = create_entity_type(
        session,
        EntityTypeCreate(
            name="Department",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "部门"},
        ),
    )
    session.commit()
    publish_resource(session, res)
    session.commit()
    assert res.status == ResourceStatus.PUBLISHED

    with pytest.raises(KGError) as exc:
        rename_resource(session, res.id, "Dept")
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION
    assert "rename_requires_draft" in str(exc.value.params)
