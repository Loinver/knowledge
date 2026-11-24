"""字典修订、显式属性引用与冻结快照。写入与引用使用同一字典行锁。"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.enum_dictionary import EnumDictionary, EnumDictionaryRevision
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    ResourceRef,
    ResourceRevision,
)
from app.schemas.enum_dictionary import (
    EnumDictionaryInput,
    EnumDictionaryOut,
    EnumDictionarySort,
    EnumReferenceOut,
)


def get_dictionary(session: Session, dictionary_id: int) -> EnumDictionary:
    item = session.get(EnumDictionary, dictionary_id, populate_existing=True)
    if item is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"dictionary_id": dictionary_id})
    return item


def lock_dictionary(session: Session, dictionary_id: int) -> EnumDictionary:
    # UPDATE 也在 SQLite 上获取写锁，避免删除与新增引用交错。
    item = session.scalar(
        update(EnumDictionary)
        .where(EnumDictionary.id == dictionary_id)
        .values(revision=EnumDictionary.revision)
        .returning(EnumDictionary)
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"dictionary_id": dictionary_id})
    return item


def check_revision(item: EnumDictionary, revision: int) -> None:
    if item.revision != revision:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"dictionary_id": item.id, "expected": revision, "actual": item.revision},
        )


def _save_revision(session: Session, item: EnumDictionary) -> None:
    session.add(
        EnumDictionaryRevision(
            dictionary_id=item.id,
            revision=item.revision,
            payload=EnumDictionaryOut.model_validate(item).model_dump(),
        )
    )
    session.flush()


def create_dictionary(session: Session, payload: EnumDictionaryInput) -> EnumDictionary:
    item = EnumDictionary(**payload.model_dump(), revision=1)
    session.add(item)
    try:
        session.flush()
    except IntegrityError as exc:
        raise KGError(ErrorCode.ALREADY_EXISTS, {"name": payload.name}) from exc
    _save_revision(session, item)
    return item


def update_dictionary(
    session: Session, dictionary_id: int, payload: EnumDictionaryInput, revision: int
) -> EnumDictionary:
    item = lock_dictionary(session, dictionary_id)
    check_revision(item, revision)
    if item.name != payload.name:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "immutable_name"})
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.revision += 1
    _save_revision(session, item)
    return item


def list_dictionaries(
    session: Session, q: str, page: int, page_size: int, sort: EnumDictionarySort
) -> tuple[list[EnumDictionary], int]:
    stmt = select(EnumDictionary)
    if q:
        # JSON text search is deliberately performed after loading the small
        # governance dictionary set. Database JSON stringification escapes
        # non-ASCII labels on SQLite, which would make a Chinese entry label
        # unsearchable; Python matching keeps SQLite/PostgreSQL behavior equal.
        query = q.casefold()
        candidates = list(session.scalars(stmt))
        dictionaries = [item for item in candidates if _matches_query(item, query)]
        total = len(dictionaries)
        column = (
            EnumDictionary.name if sort.lstrip("-") == "name" else EnumDictionary.id
        )
        dictionaries.sort(
            key=lambda item: item.name if column is EnumDictionary.name else item.id,
            reverse=sort.startswith("-"),
        )
        start = (page - 1) * page_size
        return dictionaries[start : start + page_size], total

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = EnumDictionary.name if sort.lstrip("-") == "name" else EnumDictionary.id
    ordering = column.desc() if sort.startswith("-") else column.asc()
    return list(
        session.scalars(
            stmt.order_by(ordering, EnumDictionary.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ), total


def _matches_query(item: EnumDictionary, query: str) -> bool:
    texts = [
        item.name,
        *item.label_i18n.values(),
        *item.definition_i18n.values(),
    ]
    for entry in item.entries:
        texts.extend([entry.get("value", ""), *entry.get("label_i18n", {}).values()])
    return any(query in str(text).casefold() for text in texts)


def list_revisions(session: Session, dictionary_id: int) -> list[EnumDictionaryOut]:
    get_dictionary(session, dictionary_id)
    return [
        EnumDictionaryOut.model_validate(item.payload)
        for item in session.scalars(
            select(EnumDictionaryRevision)
            .where(EnumDictionaryRevision.dictionary_id == dictionary_id)
            .order_by(EnumDictionaryRevision.revision.desc())
        )
    ]


def get_snapshot(session: Session, dictionary_id: int, revision: int) -> dict:
    snapshot = session.get(EnumDictionaryRevision, (dictionary_id, revision))
    if snapshot is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {"dictionary_id": dictionary_id, "revision": revision},
        )
    return deepcopy(snapshot.payload)


def resolve_reference(
    session: Session,
    datatype: str,
    dictionary_id: int | None,
    revision: int | None,
    default_value: str | None,
) -> int | None:
    if datatype != "enum":
        if dictionary_id is not None or revision is not None:
            raise KGError(
                ErrorCode.INVALID_REQUEST, {"reason": "enum_requires_enum_datatype"}
            )
        return None
    if dictionary_id is None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "enum_dictionary_required"})
    if revision is None:
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"reason": "enum_dictionary_revision_required"},
        )
    # 这里只为取字典行锁（副作用），返回值本身不用。
    lock_dictionary(session, dictionary_id)
    pin = revision
    snapshot = get_snapshot(session, dictionary_id, pin)
    if default_value is not None and default_value not in {
        entry["value"] for entry in snapshot["entries"]
    }:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {
                "reason": "enum_default_not_in_dictionary",
                "dictionary_id": dictionary_id,
            },
        )
    return pin


def list_references(session: Session, dictionary_id: int) -> list[EnumReferenceOut]:
    item = get_dictionary(session, dictionary_id)
    rows = session.execute(
        select(ModelResource, DatatypePropDetail)
        .join(ResourceRef, ResourceRef.source_id == ModelResource.id)
        .join(
            DatatypePropDetail, DatatypePropDetail.resource_id == ResourceRef.target_id
        )
        .where(
            DatatypePropDetail.enum_dict_id == dictionary_id,
            ResourceRef.role.in_(["data_prop", "assoc_attribute"]),
        )
        .order_by(ModelResource.id, DatatypePropDetail.resource_id)
    )
    return [
        EnumReferenceOut(
            resource_id=owner.id,
            resource_name=owner.name,
            resource_kind=owner.kind,
            resource_status=owner.status,
            property_id=detail.resource_id,
            property_name=detail.prop_name,
            enum_dict_revision=detail.enum_dict_revision,
            latest_revision=item.revision,
        )
        for owner, detail in rows
    ]


def delete_dictionary(session: Session, dictionary_id: int, revision: int) -> None:
    item = lock_dictionary(session, dictionary_id)
    check_revision(item, revision)
    live_refs = set(
        session.scalars(
            select(DatatypePropDetail.resource_id)
            .where(DatatypePropDetail.enum_dict_id == dictionary_id)
            .distinct()
        )
    )
    # 历史发布版本也算引用；不能因为当前草稿移除了属性就破坏历史追溯。
    frozen_refs = {
        resource_id
        for resource_id, payload in session.execute(
            select(ResourceRevision.resource_id, ResourceRevision.payload)
        )
        if any(
            prop.get("enum_dict_id") == dictionary_id
            for prop in (payload or {}).get("datatype_props", [])
        )
    }
    count = len(live_refs | frozen_refs)
    if count:
        raise KGError(
            ErrorCode.RESOURCE_IN_USE,
            {
                "dictionary_id": dictionary_id,
                "count": count,
                "reason": "enum_dictionary_in_use",
            },
        )
    session.execute(
        delete(EnumDictionaryRevision).where(
            EnumDictionaryRevision.dictionary_id == dictionary_id
        )
    )
    session.delete(item)
    session.flush()
