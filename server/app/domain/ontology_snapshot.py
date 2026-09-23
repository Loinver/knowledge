"""校验使用的已发布资源快照；缺失版本或结构时不回退到当前资源。"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.status_service import get_revision
from app.models.domain import OntologyRevision
from app.models.enums import ResourceKind
from app.schemas.enum_dictionary import EnumDictionaryOut


class SnapshotRef(BaseModel):
    target_id: int
    role: str


class SnapshotProperty(BaseModel):
    role: str
    name: str
    iri: str
    datatype: str
    nullable: bool
    enum_dict_id: int | None = None
    enum_dict_revision: int | None = None
    enum_dictionary: EnumDictionaryOut | None = None


class ResourceSnapshot(BaseModel):
    id: int
    name: str
    iri: str
    kind: ResourceKind
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    namespace: dict[str, str]
    parent_ids: list[int]
    resource_refs: list[SnapshotRef]
    datatype_props: list[SnapshotProperty] = Field(default_factory=list)


def load_resource_snapshot(
    session: Session, resource_id: int, revision: int
) -> ResourceSnapshot:
    frozen = get_revision(session, resource_id, revision)
    if not isinstance(frozen.payload, dict):
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"resource_id": resource_id, "reason": "invalid_snapshot_structure"},
        )
    required = {"name", "iri", "kind", "namespace", "parent_ids", "resource_refs"}
    missing = sorted(required - frozen.payload.keys())
    if missing:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {
                "resource_id": resource_id,
                "reason": "missing_snapshot_structure",
                "fields": missing,
            },
        )
    try:
        snapshot = ResourceSnapshot.model_validate(
            {**frozen.payload, "id": resource_id}
        )
    except ValidationError as exc:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"resource_id": resource_id, "reason": "invalid_snapshot_structure"},
        ) from exc
    if snapshot.kind in {ResourceKind.ENTITY, ResourceKind.ASSOC}:
        # Every local attribute reference has one frozen detail. An omitted list
        # or entry is lost validation data, not an old-style global property.
        expected_roles = Counter(
            ref.role
            for ref in snapshot.resource_refs
            if ref.role in {"data_prop", "assoc_attribute"}
        )
        props = snapshot.datatype_props
        if (
            expected_roles != Counter(prop.role for prop in props)
            or len({prop.name for prop in props}) != len(props)
            or len({prop.iri for prop in props}) != len(props)
        ):
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"resource_id": resource_id, "reason": "incomplete_property_snapshot"},
            )
    for prop in snapshot.datatype_props:
        if prop.datatype != "enum":
            continue
        dictionary = prop.enum_dictionary
        if (
            dictionary is None
            or dictionary.id != prop.enum_dict_id
            or dictionary.revision != prop.enum_dict_revision
        ):
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {
                    "resource_id": resource_id,
                    "property": prop.name,
                    "reason": "missing_or_invalid_enum_snapshot",
                },
            )
    return snapshot


def load_ontology_snapshot(
    session: Session, ontology_id: int, revision: int
) -> dict[int, ResourceSnapshot]:
    published = session.scalar(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == ontology_id,
            OntologyRevision.revision == revision,
        )
    )
    if published is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {"ontology_id": ontology_id, "revision": revision},
        )
    if not isinstance(published.resource_versions, dict):
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"ontology_id": ontology_id, "reason": "invalid_resource_versions"},
        )
    snapshots: dict[int, ResourceSnapshot] = {}
    for resource_id, pin in published.resource_versions.items():
        try:
            rid = int(resource_id)
        except (TypeError, ValueError) as exc:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"ontology_id": ontology_id, "reason": "invalid_resource_versions"},
            ) from exc
        if rid < 1 or type(pin) is not int or pin < 1:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"ontology_id": ontology_id, "reason": "invalid_resource_versions"},
            )
        snapshots[rid] = load_resource_snapshot(session, rid, pin)
    missing = sorted(
        set(published.ref_domains + published.ref_types) - snapshots.keys()
    )
    if missing:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {
                "ontology_id": ontology_id,
                "reason": "missing_resource_versions",
                "resource_ids": missing,
            },
        )
    return snapshots


def relation_endpoints(
    resource: ResourceSnapshot, resource_iris: dict[int, str]
) -> tuple[str | None, str | None]:
    """结构引用优先；早期版本内嵌的端点 IRI 仍只从该冻结版本读取。"""
    endpoints = dict(resource.definition_i18n or {})
    for ref in resource.resource_refs:
        if ref.role not in {"relation_domain", "relation_range"}:
            continue
        target_iri = resource_iris.get(ref.target_id)
        if target_iri is None:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {
                    "resource_id": resource.id,
                    "target_id": ref.target_id,
                    "reason": "incomplete_snapshot_closure",
                },
            )
        key = "domain_iri" if ref.role == "relation_domain" else "range_iri"
        endpoints[key] = target_iri
    return endpoints.get("domain_iri"), endpoints.get("range_iri")
