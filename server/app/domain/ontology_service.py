"""本体装配与设计器领域服务（H-13）。"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import func, select, update
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.template_service import (
    lock_template,
    template_resources,
    validate_resources,
)
from app.models.domain import (
    CanvasLayout,
    Ontology,
    OntologyResourceRef,
    OntologyRevision,
    OntologyRuleRef,
)
from app.models.enums import ResourceStatus
from app.models.governance import Rule
from app.models.resource import ModelResource
from app.schemas.ontology import (
    ConflictInfo,
    OntologyCreate,
    OntologyRefAdd,
    OntologyUpdate,
)


def create_ontology(session: Session, payload: OntologyCreate) -> Ontology:
    """创建本体。name 唯一。引用资源按 IRI 去重。"""
    existing = session.execute(
        select(Ontology).where(Ontology.name == payload.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"name": payload.name, "reason": "ontology_name_taken"},
        )
    pins: dict[int, int | None] = {}
    if payload.template_id is not None:
        template = lock_template(session, payload.template_id)
        resources = template_resources(template)
        validate_resources(session, resources)
        pins = {ref.resource_id: ref.pinned_revision for ref in resources}
    for resource_id in payload.ref_resource_ids:
        if resource_id in pins:
            resource = session.get(ModelResource, resource_id)
            if resource is None or resource.current_revision != pins[resource_id]:
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION,
                    {
                        "reason": "template_version_conflict",
                        "resource_id": resource_id,
                    },
                )
        else:
            pins[resource_id] = None
    rule_ids = sorted(set(payload.rule_ids))
    if len(rule_ids) != len(payload.rule_ids):
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "duplicate_rule_reference"})
    for rule_id in rule_ids:
        if session.get(Rule, rule_id) is None:
            raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"rule_id": rule_id})
    onto = Ontology(
        name=payload.name,
        iri=payload.iri,
        label_i18n=payload.label_i18n,
        definition_i18n=payload.definition_i18n,
        status=ResourceStatus.DRAFT,
        template_id=payload.template_id,
    )
    session.add(onto)
    session.flush()
    for rule_id in rule_ids:
        rule = session.get(Rule, rule_id)
        assert rule is not None
        session.add(
            OntologyRuleRef(
                ontology_id=onto.id, rule_id=rule.id, pinned_revision=rule.revision
            )
        )
    for rid, pin in pins.items():
        add_ref(session, onto.id, OntologyRefAdd(resource_id=rid, pinned_revision=pin))
    session.flush()
    return onto


def add_ref(
    session: Session, ontology_id: int, payload: OntologyRefAdd
) -> OntologyResourceRef:
    """添加引用资源。按 IRI 去重；相同资源不兼容版本显式冲突。"""
    lock_ontology_edit(
        session, get_ontology(session, ontology_id), payload.if_edit_match
    )
    resource = session.get(ModelResource, payload.resource_id)
    if resource is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"resource_id": payload.resource_id},
        )
    existing = session.execute(
        select(OntologyResourceRef).where(
            OntologyResourceRef.ontology_id == ontology_id,
            OntologyResourceRef.resource_id == payload.resource_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (
            payload.pinned_revision is not None
            and existing.pinned_revision is not None
            and payload.pinned_revision != existing.pinned_revision
        ):
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {
                    "resource_id": payload.resource_id,
                    "resource_name": resource.name,
                    "existing_revision": existing.pinned_revision,
                    "new_revision": payload.pinned_revision,
                },
            )
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"resource_id": payload.resource_id, "reason": "ref_exists"},
        )
    ref = OntologyResourceRef(
        ontology_id=ontology_id,
        resource_id=payload.resource_id,
        pinned_revision=payload.pinned_revision,
    )
    session.add(ref)
    session.flush()
    return ref


def remove_ref(
    session: Session,
    ontology_id: int,
    ref_id: int,
    if_edit_match: int | None = None,
) -> None:
    lock_ontology_edit(session, get_ontology(session, ontology_id), if_edit_match)
    ref = session.get(OntologyResourceRef, ref_id)
    if ref is None or ref.ontology_id != ontology_id:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ref_id": ref_id})
    session.delete(ref)
    session.flush()


def list_refs(session: Session, ontology_id: int) -> list[OntologyResourceRef]:
    return list(
        session.execute(
            select(OntologyResourceRef).where(
                OntologyResourceRef.ontology_id == ontology_id
            )
        ).scalars()
    )


def get_ontology(session: Session, ontology_id: int) -> Ontology:
    onto = session.get(Ontology, ontology_id)
    if onto is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": ontology_id})
    return onto


def list_rules(
    session: Session, ontology_id: int
) -> list[tuple[Rule, OntologyRuleRef]]:
    get_ontology(session, ontology_id)
    return list(
        session.execute(
            select(Rule, OntologyRuleRef)
            .join(OntologyRuleRef, OntologyRuleRef.rule_id == Rule.id)
            .where(OntologyRuleRef.ontology_id == ontology_id)
            .order_by(Rule.id)
        ).tuples()
    )


def list_ontologies(
    session: Session, q: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[Ontology], int]:
    stmt = select(Ontology)
    if q:
        stmt = stmt.where(Ontology.name.ilike(f"%{q}%"))
    count_stmt = select(func.count()).select_from(Ontology)
    if q:
        count_stmt = count_stmt.where(Ontology.name.ilike(f"%{q}%"))
    total = session.scalar(count_stmt) or 0
    stmt = stmt.order_by(Ontology.name).offset((page - 1) * page_size).limit(page_size)
    items = list(session.execute(stmt).scalars())
    return items, total


def lock_ontology_edit(
    session: Session,
    onto: Ontology,
    if_edit_match: int | None = None,
    *,
    if_match: int | None = None,
) -> Ontology:
    """Lock the parent; edit tokens do not change frozen semantic revisions."""
    stmt = update(Ontology).where(Ontology.id == onto.id)
    if if_match is not None:
        stmt = stmt.where(Ontology.current_revision == if_match)
    if if_edit_match is not None:
        stmt = stmt.where(Ontology.edit_revision == if_edit_match)
    locked = session.scalar(
        stmt.values(edit_revision=Ontology.edit_revision + 1)
        .returning(Ontology)
        .execution_options(populate_existing=True)
    )
    if locked is not None:
        return locked
    session.refresh(onto)
    if if_match is not None and onto.current_revision != if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "resource": onto.name,
                "expected": if_match,
                "actual": onto.current_revision,
            },
        )
    raise KGError(
        ErrorCode.REVISION_CONFLICT,
        {
            "resource": onto.name,
            "expected": if_edit_match,
            "actual": onto.edit_revision,
        },
    )


def update_ontology(
    session: Session, onto: Ontology, payload: OntologyUpdate
) -> Ontology:
    onto = lock_ontology_edit(
        session, onto, payload.if_edit_match, if_match=payload.if_match
    )
    if payload.label_i18n is not None:
        onto.label_i18n = payload.label_i18n
    if payload.definition_i18n is not None:
        onto.definition_i18n = payload.definition_i18n
    if payload.rule_ids is not None:
        rule_ids = sorted(set(payload.rule_ids))
        if len(rule_ids) != len(payload.rule_ids):
            raise KGError(
                ErrorCode.INVALID_REQUEST, {"reason": "duplicate_rule_reference"}
            )
        for rule_id in rule_ids:
            if session.get(Rule, rule_id) is None:
                raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"rule_id": rule_id})
        session.query(OntologyRuleRef).filter(
            OntologyRuleRef.ontology_id == onto.id
        ).delete()
        for rule_id in rule_ids:
            rule = session.get(Rule, rule_id)
            assert rule is not None
            session.add(
                OntologyRuleRef(
                    ontology_id=onto.id, rule_id=rule.id, pinned_revision=rule.revision
                )
            )
    session.flush()
    return onto


def get_canvas_layout(session: Session, scope: str, owner_id: int) -> CanvasLayout:
    """取画布布局。不存在返回空布局。"""
    layout = session.execute(
        select(CanvasLayout).where(
            CanvasLayout.scope == scope,
            CanvasLayout.owner_id == owner_id,
        )
    ).scalar_one_or_none()
    if layout is None:
        layout = CanvasLayout(scope=scope, owner_id=owner_id, positions={})
        session.add(layout)
        session.flush()
    return layout


def update_canvas_layout(
    session: Session, scope: str, owner_id: int, positions: dict
) -> CanvasLayout:
    """更新画布布局。拖节点只改这里，不产生语义版本。"""
    layout = get_canvas_layout(session, scope, owner_id)
    layout.positions = positions
    session.flush()
    return layout


def publish_ontology(
    session: Session, onto: Ontology, if_edit_match: int | None = None
) -> int:
    """发布本体：冻结全部成员资源的版本号到 resource_versions 快照。

    版本冻结：发布时记录每个引用资源的 current_revision，
    上游资源升级产生新版本时，已发布本体不随动。
    """
    onto = lock_ontology_edit(session, onto, if_edit_match)
    refs = list_refs(session, onto.id)
    ref_domains: list[int] = []
    ref_types: list[int] = []
    resource_versions: dict[str, int] = {}
    for ref in refs:
        res = session.get(ModelResource, ref.resource_id)
        if res is None:
            raise KGError(
                ErrorCode.RESOURCE_NOT_FOUND,
                {"resource_id": ref.resource_id},
            )
        if res.status != ResourceStatus.PUBLISHED:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {
                    "resource": res.name,
                    "reason": "member_not_published",
                },
            )
        pinned = ref.pinned_revision or res.current_revision
        resource_versions[str(ref.resource_id)] = pinned
        from app.models.enums import ResourceKind

        if res.kind == ResourceKind.DOMAIN:
            ref_domains.append(ref.resource_id)
        else:
            ref_types.append(ref.resource_id)
    new_rev = onto.current_revision + 1
    rule_rows = []
    if sqlalchemy_inspect(session.get_bind()).has_table("ontology_rule_ref"):
        rule_rows = list(
            session.execute(
                select(Rule, OntologyRuleRef)
                .join(OntologyRuleRef, OntologyRuleRef.rule_id == Rule.id)
                .where(OntologyRuleRef.ontology_id == onto.id)
                .order_by(Rule.id)
            )
        )
    rev = OntologyRevision(
        ontology_id=onto.id,
        revision=new_rev,
        ref_domains=ref_domains,
        ref_types=ref_types,
        rules=[
            {
                "rule_id": rule.id,
                "identifier": rule.identifier,
                "revision": rule.revision,
                "source_kind": rule.source_kind,
                "source_reference": rule.source_reference,
            }
            for rule, ref in rule_rows
        ],
        resource_versions=resource_versions,
        metadata_snapshot={
            "name": onto.name,
            "iri": onto.iri,
            "label_i18n": deepcopy(onto.label_i18n),
            "definition_i18n": deepcopy(onto.definition_i18n),
        },
    )
    session.add(rev)
    onto.current_revision = new_rev
    onto.status = ResourceStatus.PUBLISHED
    session.flush()
    return new_rev


def detect_conflicts(session: Session, ontology_id: int) -> list[ConflictInfo]:
    """检测相同资源不兼容版本冲突。"""
    refs = list_refs(session, ontology_id)
    conflicts: list[ConflictInfo] = []
    seen: dict[int, int] = {}
    for ref in refs:
        res = session.get(ModelResource, ref.resource_id)
        if res is None:
            continue
        pinned = ref.pinned_revision or res.current_revision
        if ref.resource_id in seen and seen[ref.resource_id] != pinned:
            conflicts.append(
                ConflictInfo(
                    resource_id=ref.resource_id,
                    resource_name=res.name,
                    existing_revision=seen[ref.resource_id],
                    new_revision=pinned,
                )
            )
        else:
            seen[ref.resource_id] = pinned
    return conflicts
