"""M1 关系类型库（H-12）测试。

覆盖 A05：跨域与多类型关系表达正确；
      A06：同一对实体两次业务关系可分别保存（关联实体模式）；
      OWL 特征兼容性校验；
      关联实体模式自动生成 ASSOC 资源。
"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.relation_service import (
    create_relation_type,
    get_assoc_attributes,
    get_relation_meta,
    list_relation_types,
    publish_relation_type,
    update_relation_type,
    validate_owl_compatibility,
)
from app.domain.type_service import create_entity_type
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import ModelResource
from app.schemas.relation import (
    CardinalitySpec,
    EndpointSpec,
    OwlFeatures,
    RelationTypeCreate,
    RelationTypeUpdate,
)
from app.schemas.type import EntityTypeCreate
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def session(tmp_path):
    url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = session_factory()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def ns(session):
    return register_namespace(session, "kg", "https://example.org/kg#")


@pytest.fixture()
def employee_type(session, ns):
    return create_entity_type(
        session,
        EntityTypeCreate(
            name="Employee",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "员工", "en-US": "Employee"},
        ),
    )


@pytest.fixture()
def department_type(session, ns):
    return create_entity_type(
        session,
        EntityTypeCreate(
            name="Department",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "部门", "en-US": "Department"},
        ),
    )


@pytest.fixture()
def project_type(session, ns):
    return create_entity_type(
        session,
        EntityTypeCreate(
            name="Project",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "项目", "en-US": "Project"},
        ),
    )


# ---------------------------------------------------------------------------
# A05 跨域与多类型关系表达正确
# ---------------------------------------------------------------------------


def test_relation_cross_domain_endpoint(session, ns, employee_type, department_type):
    """A05：关系端点可引用不同实体类型（跨域）。"""
    rel = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksIn",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于", "en-US": "works in"},
            domain_spec=EndpointSpec(
                type_id=employee_type.id,
                cardinality=CardinalitySpec(
                    min=0,
                    max=1,
                    role_label_i18n={"zh-CN": "每个员工最多1个部门"},
                ),
            ),
            range_spec=EndpointSpec(
                type_id=department_type.id,
                cardinality=CardinalitySpec(
                    min=0,
                    max=-1,
                    role_label_i18n={"zh-CN": "每个部门可有N个员工"},
                ),
            ),
        ),
    )
    session.commit()
    assert rel.kind == ResourceKind.OBJECT_PROP
    assert rel.iri == "https://example.org/kg#WorksIn"
    meta = get_relation_meta(session, rel)
    assert employee_type.id in meta["domain_ids"]
    assert department_type.id in meta["range_ids"]


def test_relation_multi_type_range(
    session, ns, employee_type, project_type, department_type
):
    """A05：同一关系可在不同关系中复用端点类型。"""
    for name, range_type in [("Manages", project_type), ("Leads", department_type)]:
        create_relation_type(
            session,
            RelationTypeCreate(
                name=name,
                namespace_id=ns.id,
                label_i18n={"zh-CN": name, "en-US": name},
                domain_spec=EndpointSpec(type_id=employee_type.id),
                range_spec=EndpointSpec(type_id=range_type.id),
            ),
        )
    session.commit()
    _items, total = list_relation_types(session)
    assert total == 2


# ---------------------------------------------------------------------------
# OWL 特征兼容性校验
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "owl,should_pass",
    [
        (OwlFeatures(), True),
        (OwlFeatures(symmetric=True), True),
        (OwlFeatures(transitive=True), True),
        (OwlFeatures(functional=True, inverse_functional=True), True),
        (OwlFeatures(symmetric=True, functional=True), False),
        (OwlFeatures(symmetric=True, inverse_functional=True), False),
        (OwlFeatures(transitive=True, functional=True), False),
        (OwlFeatures(transitive=True, inverse_functional=True), False),
    ],
)
def test_owl_compatibility(owl: OwlFeatures, should_pass: bool) -> None:
    if should_pass:
        validate_owl_compatibility(owl)
    else:
        with pytest.raises(KGError) as exc:
            validate_owl_compatibility(owl)
        assert exc.value.code == ErrorCode.VALIDATION_VIOLATION
        assert "owl_conflicts" in exc.value.params


def test_create_relation_rejects_incompatible_owl(
    session, ns, employee_type, department_type
):
    """创建时 OWL 不兼容组合应被拦截。"""
    with pytest.raises(KGError) as exc:
        create_relation_type(
            session,
            RelationTypeCreate(
                name="BadRel",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "坏关系"},
                domain_spec=EndpointSpec(type_id=employee_type.id),
                range_spec=EndpointSpec(type_id=department_type.id),
                owl=OwlFeatures(symmetric=True, functional=True),
            ),
        )
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


# ---------------------------------------------------------------------------
# A06 关联实体模式：启用关系属性时生成 ASSOC 资源
# ---------------------------------------------------------------------------


def test_enable_attributes_generates_assoc_resource(
    session, ns, employee_type, department_type
):
    """启用关系属性 → 自动生成 ASSOC 资源 + 端点角色。"""
    rel = create_relation_type(
        session,
        RelationTypeCreate(
            name="Participates",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "参与", "en-US": "participates"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
            enable_attributes=True,
            attribute_defs=[
                {"name": "role", "datatype": "string", "nullable": False},
                {"name": "since", "datatype": "date", "nullable": True},
            ],
        ),
    )
    session.commit()
    meta = get_relation_meta(session, rel)
    assert meta["assoc_resource_id"] is not None
    assoc = session.get(ModelResource, meta["assoc_resource_id"])
    assert assoc is not None
    assert assoc.kind == ResourceKind.ASSOC
    assert assoc.name == "ParticipatesAssociation"
    attrs = get_assoc_attributes(session, assoc)
    assert len(attrs) == 2
    attr_names = {a.name for a in attrs}
    assert "role" in attr_names
    assert "since" in attr_names


def test_no_attributes_no_assoc_resource(session, ns, employee_type, department_type):
    """不启用关系属性时不生成 ASSOC。"""
    rel = create_relation_type(
        session,
        RelationTypeCreate(
            name="BelongsTo",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "属于"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
            enable_attributes=False,
        ),
    )
    session.commit()
    meta = get_relation_meta(session, rel)
    assert meta["assoc_resource_id"] is None


def test_two_relations_same_entity_pair_both_saved(
    session, ns, employee_type, department_type
):
    """A06：同一对实体类型两次业务关系分别保存，不被去重。

    例如 Employee-Department 既有"就职于"又有"管理"，两条关系
    各自是独立的 OBJECT_PROP 资源，关联实体模式下各自有独立 ASSOC。
    """
    rel1 = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksIn",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
            enable_attributes=True,
            attribute_defs=[{"name": "since", "datatype": "date"}],
        ),
    )
    rel2 = create_relation_type(
        session,
        RelationTypeCreate(
            name="Manages",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "管理"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
            enable_attributes=True,
            attribute_defs=[{"name": "tenure", "datatype": "string"}],
        ),
    )
    session.commit()
    # 两条关系独立存在
    assert rel1.id != rel2.id
    assert rel1.name == "WorksIn"
    assert rel2.name == "Manages"
    # 各自的 ASSOC 资源也独立
    meta1 = get_relation_meta(session, rel1)
    meta2 = get_relation_meta(session, rel2)
    assert meta1["assoc_resource_id"] != meta2["assoc_resource_id"]
    assoc1 = session.get(ModelResource, meta1["assoc_resource_id"])
    assoc2 = session.get(ModelResource, meta2["assoc_resource_id"])
    assert assoc1.name == "WorksInAssociation"
    assert assoc2.name == "ManagesAssociation"


# ---------------------------------------------------------------------------
# 基数与逆关系
# ---------------------------------------------------------------------------


def test_cardinality_direction_noted(session, ns, employee_type, department_type):
    """基数注明约束方向：domain/range 各持 CardinalitySpec。"""
    rel = create_relation_type(
        session,
        RelationTypeCreate(
            name="HasMember",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "有成员"},
            domain_spec=EndpointSpec(
                type_id=department_type.id,
                cardinality=CardinalitySpec(
                    min=0,
                    max=-1,
                    role_label_i18n={"zh-CN": "每个部门可有N个员工"},
                ),
            ),
            range_spec=EndpointSpec(
                type_id=employee_type.id,
                cardinality=CardinalitySpec(
                    min=0,
                    max=1,
                    role_label_i18n={"zh-CN": "每个员工最多1个部门"},
                ),
            ),
        ),
    )
    session.commit()
    assert rel.id is not None


def test_inverse_of(session, ns, employee_type, department_type):
    """逆关系：inverse_of 指向另一个关系类型。"""
    rel1 = create_relation_type(
        session,
        RelationTypeCreate(
            name="Manages",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "管理"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
        ),
    )
    session.commit()
    rel2 = create_relation_type(
        session,
        RelationTypeCreate(
            name="ManagedBy",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "被管理"},
            domain_spec=EndpointSpec(type_id=department_type.id),
            range_spec=EndpointSpec(type_id=employee_type.id),
            inverse_of=rel1.id,
        ),
    )
    session.commit()
    meta = get_relation_meta(session, rel2)
    assert meta["inverse_of"] == rel1.id


def test_inverse_of_must_be_relation(session, ns, employee_type, department_type):
    """inverse_of 指向非关系类型应被拒。"""
    with pytest.raises(KGError) as exc:
        create_relation_type(
            session,
            RelationTypeCreate(
                name="BadInverse",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "坏逆关系"},
                domain_spec=EndpointSpec(type_id=employee_type.id),
                range_spec=EndpointSpec(type_id=department_type.id),
                inverse_of=employee_type.id,  # 实体类型，不是关系
            ),
        )
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


# ---------------------------------------------------------------------------
# 状态机与乐观锁
# ---------------------------------------------------------------------------


def test_publish_freezes_relation(session, ns, employee_type, department_type):
    """发布关系类型：冻结不可变版本。"""
    rel = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksIn",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
        ),
    )
    session.commit()
    rev = publish_relation_type(session, rel)
    session.commit()
    assert rev == 1
    assert rel.status == ResourceStatus.PUBLISHED
    assert rel.current_revision == 1


def test_update_requires_if_match(session, ns, employee_type, department_type):
    """更新关系必须带 If-Match。"""
    rel = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksIn",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
        ),
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        update_relation_type(
            session,
            rel,
            RelationTypeUpdate(label_i18n={"zh-CN": "新名"}, if_match=99),
        )
    assert exc.value.code == ErrorCode.REVISION_CONFLICT


def test_update_revision_conflict(session, ns, employee_type, department_type):
    """If-Match 不匹配返回 REVISION_CONFLICT。"""
    rel = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksIn",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
        ),
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        update_relation_type(
            session,
            rel,
            RelationTypeUpdate(label_i18n={"zh-CN": "新"}, if_match=99),
        )
    assert exc.value.code == ErrorCode.REVISION_CONFLICT


def test_endpoint_must_be_entity_type(session, ns, employee_type, department_type):
    """端点引用必须是 ENTITY 类型。"""
    # 先建一个关系类型，再试图用它做端点
    rel1 = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksIn",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
        ),
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        create_relation_type(
            session,
            RelationTypeCreate(
                name="BadEndpoint",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "坏端点"},
                domain_spec=EndpointSpec(type_id=rel1.id),  # 关系类型不是实体
                range_spec=EndpointSpec(type_id=department_type.id),
            ),
        )
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND


def test_duplicate_name_rejected(session, ns, employee_type, department_type):
    """重复 name 不可创建。"""
    create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksIn",
            namespace_id=ns.id,
            label_i18n={"zh-CN": "就职于"},
            domain_spec=EndpointSpec(type_id=employee_type.id),
            range_spec=EndpointSpec(type_id=department_type.id),
        ),
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        create_relation_type(
            session,
            RelationTypeCreate(
                name="WorksIn",
                namespace_id=ns.id,
                label_i18n={"zh-CN": "重复"},
                domain_spec=EndpointSpec(type_id=employee_type.id),
                range_spec=EndpointSpec(type_id=department_type.id),
            ),
        )
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED
