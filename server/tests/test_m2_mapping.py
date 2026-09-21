"""映射方案集成测试（H-30）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.mapping_service import (
    create_mapping,
    delete_mapping,
    get_draft_revision,
    get_mapping,
    get_published_revision,
    list_mappings,
    publish_mapping,
    save_draft,
)
from app.models.domain import Ontology
from app.models.enums import ResourceStatus
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
    NullPolicy,
    RelEndpointSpec,
    RelMapCreate,
    RelMode,
    TransformKind,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def session(tmp_path):
    url = f"sqlite:///{tmp_path}/kg.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = sf()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


def _make_ontology(session, name="onto1", published=True):
    onto = Ontology(
        name=name,
        iri=f"https://example.org/onto/{name}",
        status=ResourceStatus.PUBLISHED if published else ResourceStatus.DRAFT,
        current_revision=1,
    )
    session.add(onto)
    session.flush()
    if published:
        # 直接造一条 OntologyRevision 让 onto_version 冻结有据
        from app.models.domain import OntologyRevision

        rev = OntologyRevision(
            ontology_id=onto.id,
            revision=1,
            ref_domains=[],
            ref_types=[],
            rules=[],
            resource_versions={},
        )
        session.add(rev)
        session.flush()
    return onto


def _em(entity_type, table, fields, key_fields=None):
    return EntityMapCreate(
        entity_type=entity_type,
        table=table,
        field_maps=[
            FieldMap(
                target_attr=a,
                source_field=f,
                transform=TransformKind.IDENTITY,
                null_policy=NullPolicy.NULLABLE,
            )
            for a, f in fields
        ],
        key_fields=key_fields or [],
    )


def test_create_mapping_with_draft(session):
    onto = _make_ontology(session)
    m = create_mapping(
        session,
        MappingCreate(
            name="m1",
            ontology_id=onto.id,
            draft=MappingRevisionCreate(
                entity_maps=[
                    _em("Enterprise", "enterprise", [("name", "name"), ("iri", "id")])
                ],
                rel_maps=[],
            ),
        ),
    )
    session.commit()
    assert m.name == "m1"
    assert m.status == ResourceStatus.DRAFT
    draft = get_draft_revision(session, m.id)
    assert draft is not None
    assert draft.revision == 0
    assert draft.onto_version == 0
    assert len(draft.entity_maps) == 1


def test_duplicate_name_rejected(session):
    onto = _make_ontology(session)
    create_mapping(session, MappingCreate(name="dup", ontology_id=onto.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        create_mapping(session, MappingCreate(name="dup", ontology_id=onto.id))
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_one_table_multiple_types(session):
    """A10：一张表生成多个实体类型。"""
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="multi", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                _em("Enterprise", "enterprise", [("name", "name")]),
                _em("EnterpriseBrief", "enterprise", [("label", "name")]),
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    draft = get_draft_revision(session, m.id)
    types = [em["entity_type"] for em in draft.entity_maps]
    assert types == ["Enterprise", "EnterpriseBrief"]
    assert all(em["table"] == "enterprise" for em in draft.entity_maps)


def test_one_type_multiple_tables(session):
    """A10：一个类型来自多张表。"""
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="multi-src", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                _em("Person", "hr_employee", [("name", "name")]),
                _em("Person", "ct_contract", [("name", "title")]),
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    draft = get_draft_revision(session, m.id)
    tables = [em["table"] for em in draft.entity_maps]
    assert "hr_employee" in tables
    assert "ct_contract" in tables


def test_relation_fk_mode(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="fk", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[],
            rel_maps=[
                RelMapCreate(
                    relation_type="works_for",
                    mode=RelMode.FK,
                    table="hr_employee",
                    fk_field="enterprise_id",
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    draft = get_draft_revision(session, m.id)
    assert draft.rel_maps[0]["mode"] == "FK"
    assert draft.rel_maps[0]["fk_field"] == "enterprise_id"


def test_relation_junction_mode(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="jun", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[],
            rel_maps=[
                RelMapCreate(
                    relation_type="contract_project",
                    mode=RelMode.JUNCTION,
                    table="ct_contract_project",
                    source=RelEndpointSpec(
                        field="contract_id", ref_table="ct_contract", ref_field="id"
                    ),
                    target=RelEndpointSpec(
                        field="project_id", ref_table="pm_project", ref_field="id"
                    ),
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    draft = get_draft_revision(session, m.id)
    rm = draft.rel_maps[0]
    assert rm["mode"] == "JUNCTION"
    assert rm["source"]["field"] == "contract_id"


def test_relation_associative_mode_with_attributes(session):
    """带属性关联表：attributes 保留。"""
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="assoc", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[],
            rel_maps=[
                RelMapCreate(
                    relation_type="project_member",
                    mode=RelMode.ASSOCIATIVE,
                    table="pm_project_member",
                    source=RelEndpointSpec(
                        field="project_id", ref_table="pm_project", ref_field="id"
                    ),
                    target=RelEndpointSpec(
                        field="member_id", ref_table="hr_employee", ref_field="id"
                    ),
                    attributes=[{"attr": "role", "field": "role"}],
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    draft = get_draft_revision(session, m.id)
    rm = draft.rel_maps[0]
    assert rm["mode"] == "ASSOCIATIVE"
    assert rm["attributes"] == [{"attr": "role", "field": "role"}]


def test_fk_mode_requires_fk_field(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="bad-fk", ontology_id=onto.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        save_draft(
            session,
            m.id,
            MappingRevisionCreate(
                entity_maps=[],
                rel_maps=[RelMapCreate(relation_type="r", mode=RelMode.FK, table="t")],
            ),
            if_match=0,
        )
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_junction_requires_endpoints(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="bad-jun", ontology_id=onto.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        save_draft(
            session,
            m.id,
            MappingRevisionCreate(
                entity_maps=[],
                rel_maps=[
                    RelMapCreate(relation_type="r", mode=RelMode.JUNCTION, table="t")
                ],
            ),
            if_match=0,
        )
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_duplicate_target_attr_rejected(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="dup-attr", ontology_id=onto.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        save_draft(
            session,
            m.id,
            MappingRevisionCreate(
                entity_maps=[
                    EntityMapCreate(
                        entity_type="E",
                        table="t",
                        field_maps=[
                            FieldMap(target_attr="x", source_field="a"),
                            FieldMap(target_attr="x", source_field="b"),
                        ],
                    )
                ],
                rel_maps=[],
            ),
            if_match=0,
        )
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_save_draft_revision_conflict(session):
    """乐观锁：if_match 不匹配报 409。"""
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="lock", ontology_id=onto.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        save_draft(
            session,
            m.id,
            MappingRevisionCreate(),
            if_match=99,
        )
    assert exc.value.code == ErrorCode.REVISION_CONFLICT


def test_publish_freezes_onto_version(session):
    """发布冻结 onto_version 到本体当前已发布版本。"""
    onto = _make_ontology(session, published=True)
    m = create_mapping(session, MappingCreate(name="pub", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(entity_maps=[_em("E", "t", [("name", "name")])]),
        if_match=0,
    )
    session.commit()
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()
    assert rev.revision == 1
    assert rev.onto_version == 1  # 冻结到本体 revision=1
    m2 = get_mapping(session, m.id)
    assert m2.status == ResourceStatus.PUBLISHED
    assert m2.current_revision == 1


def test_publish_requires_published_ontology(session):
    """本体未发布时映射发布失败。"""
    onto = _make_ontology(session, published=False)
    m = create_mapping(session, MappingCreate(name="noonto", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(entity_maps=[_em("E", "t", [("name", "name")])]),
        if_match=0,
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        publish_mapping(session, m.id, if_match=0)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_publish_requires_draft(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="nodraft", ontology_id=onto.id))
    session.commit()
    with pytest.raises(KGError) as exc:
        publish_mapping(session, m.id, if_match=0)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_published_mapping_immutable(session):
    """已发布映射不可再改草稿。"""
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="imm", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(entity_maps=[_em("E", "t", [("name", "name")])]),
        if_match=0,
    )
    session.commit()
    publish_mapping(session, m.id, if_match=0)
    session.commit()
    with pytest.raises(KGError) as exc:
        save_draft(session, m.id, MappingRevisionCreate(), if_match=1)
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_published_revision_retrievable(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="ret", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(entity_maps=[_em("E", "t", [("name", "name")])]),
        if_match=0,
    )
    session.commit()
    publish_mapping(session, m.id, if_match=0)
    session.commit()
    rev = get_published_revision(session, m.id)
    assert rev.revision == 1
    assert rev.onto_version == 1


def test_save_draft_overwrites_previous_draft(session):
    """重复保存草稿覆盖旧草稿，不产生新 revision。"""
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="ow", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(entity_maps=[_em("E", "t", [("name", "name")])]),
        if_match=0,
    )
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(entity_maps=[_em("F", "t", [("x", "x")])]),
        if_match=0,
    )
    session.commit()
    draft = get_draft_revision(session, m.id)
    assert draft.entity_maps[0]["entity_type"] == "F"
    # 只有一条 revision=0
    from app.models.data_access import MappingRevision
    from sqlalchemy import select

    drafts = list(
        session.execute(
            select(MappingRevision).where(
                MappingRevision.mapping_id == m.id, MappingRevision.revision == 0
            )
        ).scalars()
    )
    assert len(drafts) == 1


def test_delete_draft_mapping(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="del", ontology_id=onto.id))
    session.commit()
    delete_mapping(session, m.id)
    session.commit()
    with pytest.raises(KGError):
        get_mapping(session, m.id)


def test_delete_published_rejected(session):
    onto = _make_ontology(session)
    m = create_mapping(session, MappingCreate(name="delpub", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(entity_maps=[_em("E", "t", [("name", "name")])]),
        if_match=0,
    )
    session.commit()
    publish_mapping(session, m.id, if_match=0)
    session.commit()
    with pytest.raises(KGError) as exc:
        delete_mapping(session, m.id)
    assert exc.value.code == ErrorCode.ALREADY_PUBLISHED


def test_list_mappings_pagination(session):
    onto = _make_ontology(session)
    for i in range(3):
        create_mapping(session, MappingCreate(name=f"item-{i}", ontology_id=onto.id))
    session.commit()
    items, total = list_mappings(session, "", page=1, page_size=2)
    assert total == 3
    assert len(items) == 2


def test_create_mapping_unknown_ontology(session):
    with pytest.raises(KGError) as exc:
        create_mapping(session, MappingCreate(name="x", ontology_id=9999))
    assert exc.value.code == ErrorCode.RESOURCE_NOT_FOUND
