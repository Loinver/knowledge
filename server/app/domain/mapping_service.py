"""映射方案领域服务（H-30）。

mapping + mapping_revision：草稿可反复改，发布生成不可变 revision 并冻结 onto_version。
实体映射一表多类型、一类型多表均支持（列表存储，不去重）。
关系三模式 FK/JUNCTION/ASSOCIATIVE 各自校验字段完整性。
版本冻结：发布时 onto_version = OntologyRevision.revision（本体当前已发布版本）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import Ontology, OntologyRevision
from app.models.enums import ResourceStatus
from app.schemas.mapping import (
    EntityMapCreate,
    MappingCreate,
    MappingRevisionCreate,
    RelMapCreate,
)


def create_mapping(session: Session, payload: MappingCreate) -> Mapping:
    """创建映射方案，可选带初始草稿。"""
    onto = session.get(Ontology, payload.ontology_id)
    if onto is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": payload.ontology_id}
        )
    _ensure_name_unique(session, payload.name)
    m = Mapping(
        name=payload.name,
        ontology_id=payload.ontology_id,
        status=ResourceStatus.DRAFT,
        current_revision=0,
    )
    session.add(m)
    session.flush()
    if payload.draft is not None:
        _save_draft_revision(session, m, payload.draft)
    return m


def _ensure_name_unique(session: Session, name: str) -> None:
    existing = session.execute(
        select(Mapping).where(Mapping.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED, {"name": name, "reason": "mapping_name_taken"}
        )


def get_mapping(session: Session, mapping_id: int) -> Mapping:
    m = session.get(Mapping, mapping_id)
    if m is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"mapping_id": mapping_id})
    return m


def list_mappings(
    session: Session, q: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[Mapping], int]:
    stmt = select(Mapping)
    if q:
        stmt = stmt.where(Mapping.name.ilike(f"%{q}%"))
    count_stmt = select(Mapping)
    if q:
        count_stmt = count_stmt.where(Mapping.name.ilike(f"%{q}%"))
    total = len(list(session.execute(count_stmt).scalars()))
    stmt = stmt.order_by(Mapping.name).offset((page - 1) * page_size).limit(page_size)
    items = list(session.execute(stmt).scalars())
    return items, total


def save_draft(
    session: Session, mapping_id: int, draft: MappingRevisionCreate, if_match: int
) -> MappingRevision:
    """保存草稿 revision。已发布的 mapping 不可再改草稿。"""
    m = get_mapping(session, mapping_id)
    if m.current_revision != if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"expected": if_match, "actual": m.current_revision},
        )
    if m.status == ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"mapping_id": mapping_id, "reason": "mapping_published_immutable"},
        )
    return _save_draft_revision(session, m, draft)


def _save_draft_revision(
    session: Session, m: Mapping, draft: MappingRevisionCreate
) -> MappingRevision:
    """草稿存为 revision=0 的可变行（同一 mapping 只有一条 revision=0 草稿）。"""
    # 校验映射结构
    for em in draft.entity_maps:
        _validate_entity_map(em)
    for rm in draft.rel_maps:
        _validate_rel_map(rm)
    # 删除旧草稿
    old_draft = session.execute(
        select(MappingRevision).where(
            MappingRevision.mapping_id == m.id,
            MappingRevision.revision == 0,
        )
    ).scalar_one_or_none()
    if old_draft is not None:
        session.delete(old_draft)
        session.flush()
    rev = MappingRevision(
        mapping_id=m.id,
        revision=0,
        onto_version=0,  # 草稿未冻结，发布时填
        entity_maps=[_em_to_dict(em) for em in draft.entity_maps],
        rel_maps=[_rm_to_dict(rm) for rm in draft.rel_maps],
    )
    session.add(rev)
    session.flush()
    return rev


def _validate_entity_map(em: EntityMapCreate) -> None:
    if not em.entity_type:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "entity_type_empty"})
    if not em.table:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "table_empty"})
    if not em.field_maps:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "field_maps_empty"})
    targets = [fm.target_attr for fm in em.field_maps]
    if len(set(targets)) != len(targets):
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"reason": "duplicate_target_attr", "entity_type": em.entity_type},
        )
    for fm in em.field_maps:
        if fm.null_policy == "REQUIRED" and not fm.source_field:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"reason": "required_field_missing_source", "attr": fm.target_attr},
            )


def _validate_rel_map(rm: RelMapCreate) -> None:
    if not rm.relation_type:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "relation_type_empty"})
    if not rm.table:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "table_empty"})
    if rm.mode == "FK":
        if not rm.fk_field:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"reason": "fk_mode_requires_fk_field", "relation": rm.relation_type},
            )
    elif rm.mode in ("JUNCTION", "ASSOCIATIVE"):
        if rm.source is None or rm.target is None:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"reason": "mode_requires_endpoints", "mode": rm.mode},
            )
    else:
        raise KGError(
            ErrorCode.INVALID_REQUEST, {"reason": "unknown_mode", "mode": rm.mode}
        )


def _em_to_dict(em: EntityMapCreate) -> dict:
    return {
        "entity_type": em.entity_type,
        "table": em.table,
        "schema": em.db_schema,
        "field_maps": [fm.model_dump() for fm in em.field_maps],
        "key_fields": em.key_fields,
    }


def _rm_to_dict(rm: RelMapCreate) -> dict:
    return {
        "relation_type": rm.relation_type,
        "mode": rm.mode,
        "table": rm.table,
        "schema": rm.db_schema,
        "fk_field": rm.fk_field,
        "source": rm.source.model_dump() if rm.source else None,
        "target": rm.target.model_dump() if rm.target else None,
        "attributes": rm.attributes,
    }


def publish_mapping(
    session: Session, mapping_id: int, if_match: int
) -> MappingRevision:
    """发布映射：冻结 onto_version，生成不可变 revision。"""
    m = get_mapping(session, mapping_id)
    if m.current_revision != if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"expected": if_match, "actual": m.current_revision},
        )
    if m.status == ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"mapping_id": mapping_id, "reason": "already_published"},
        )
    # 取本体当前已发布版本
    onto = session.get(Ontology, m.ontology_id)
    if onto is None or onto.status != ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"ontology_id": m.ontology_id, "reason": "ontology_not_published"},
        )
    onto_rev = (
        session.execute(
            select(OntologyRevision)
            .where(OntologyRevision.ontology_id == onto.id)
            .order_by(OntologyRevision.revision.desc())
        )
        .scalars()
        .first()
    )
    if onto_rev is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"ontology_id": onto.id, "reason": "no_ontology_revision"},
        )
    # 取草稿
    draft = session.execute(
        select(MappingRevision).where(
            MappingRevision.mapping_id == m.id,
            MappingRevision.revision == 0,
        )
    ).scalar_one_or_none()
    if draft is None:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"mapping_id": m.id, "reason": "no_draft_to_publish"},
        )
    new_rev = m.current_revision + 1
    frozen = MappingRevision(
        mapping_id=m.id,
        revision=new_rev,
        onto_version=onto_rev.revision,  # 版本冻结
        entity_maps=list(draft.entity_maps),
        rel_maps=list(draft.rel_maps),
    )
    session.add(frozen)
    m.current_revision = new_rev
    m.status = ResourceStatus.PUBLISHED
    session.flush()
    return frozen


def get_published_revision(session: Session, mapping_id: int) -> MappingRevision:
    """取已发布的最新 revision（revision > 0 中最大）。"""
    rev = (
        session.execute(
            select(MappingRevision)
            .where(
                MappingRevision.mapping_id == mapping_id, MappingRevision.revision > 0
            )
            .order_by(MappingRevision.revision.desc())
        )
        .scalars()
        .first()
    )
    if rev is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {"mapping_id": mapping_id, "reason": "no_published_revision"},
        )
    return rev


def get_draft_revision(session: Session, mapping_id: int) -> MappingRevision | None:
    return session.execute(
        select(MappingRevision).where(
            MappingRevision.mapping_id == mapping_id,
            MappingRevision.revision == 0,
        )
    ).scalar_one_or_none()


def delete_mapping(session: Session, mapping_id: int) -> None:
    m = get_mapping(session, mapping_id)
    if m.status == ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"mapping_id": mapping_id, "reason": "published_not_deletable"},
        )
    session.delete(m)
    session.flush()
