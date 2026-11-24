"""M-02 标准核心类型/对象属性逐项核对。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_snapshot import ResourceSnapshot, load_resource_snapshot
from app.domain.template_service import get_template, template_resources
from app.models.governance import StandardClause
from app.models.resource import ModelResource, Namespace
from app.schemas.core_check import CoreCheckItem, CoreCheckOut, CoreCheckRequest


def check_template_core(
    session: Session, template_id: int, payload: CoreCheckRequest
) -> CoreCheckOut:
    template = get_template(session, template_id)
    requirements = {item.name: item for item in payload.requirements}
    if len(requirements) != len(payload.requirements):
        raise KGError(
            ErrorCode.INVALID_REQUEST, {"reason": "duplicate_core_requirement"}
        )
    for requirement in payload.requirements:
        if session.get(StandardClause, requirement.standard_clause_id) is None:
            raise KGError(
                ErrorCode.RESOURCE_NOT_FOUND,
                {"standard_clause_id": requirement.standard_clause_id},
            )

    by_name: dict[str, tuple[ResourceSnapshot, int, int]] = {}
    for reference in template_resources(template):
        resource = session.get(ModelResource, reference.resource_id)
        if resource is None:
            raise KGError(
                ErrorCode.RESOURCE_NOT_FOUND, {"resource_id": reference.resource_id}
            )
        snapshot = load_resource_snapshot(
            session, resource.id, reference.pinned_revision
        )
        # Inspect the pinned template member, never mutable name/kind metadata.
        by_name[snapshot.name] = (
            snapshot,
            reference.pinned_revision,
            resource.namespace_id,
        )

    items: list[CoreCheckItem] = []
    for requirement in payload.requirements:
        found = by_name.get(requirement.name)
        if found is None:
            items.append(
                CoreCheckItem(
                    name=requirement.name,
                    kind=requirement.kind,
                    state="MISSING",
                    standard_clause_id=requirement.standard_clause_id,
                    reason="resource_not_in_template",
                )
            )
            continue
        snapshot, pinned_revision, _namespace_id = found
        if snapshot.kind != requirement.kind:
            items.append(
                CoreCheckItem(
                    name=snapshot.name,
                    kind=snapshot.kind,
                    state="KIND_MISMATCH",
                    resource_id=snapshot.id,
                    pinned_revision=pinned_revision,
                    standard_clause_id=requirement.standard_clause_id,
                    reason="resource_kind_differs",
                )
            )
            continue
        items.append(
            CoreCheckItem(
                name=snapshot.name,
                kind=snapshot.kind,
                state="PRESENT",
                resource_id=snapshot.id,
                pinned_revision=pinned_revision,
                standard_clause_id=requirement.standard_clause_id,
            )
        )

    for name, (snapshot, pinned_revision, namespace_id) in by_name.items():
        if name in requirements:
            continue
        namespace = session.get(Namespace, namespace_id)
        items.append(
            CoreCheckItem(
                name=name,
                kind=snapshot.kind,
                state="ENTERPRISE_EXTENSION"
                if namespace is None or not namespace.protected
                else "PRESENT",
                resource_id=snapshot.id,
                pinned_revision=pinned_revision,
                reason="not_in_standard_requirement",
            )
        )

    core_items = [item for item in items if item.standard_clause_id is not None]
    return CoreCheckOut(
        template_id=template.id,
        template_revision=template.revision,
        items=items,
        all_core_present=all(item.state == "PRESENT" for item in core_items),
        enterprise_extension_count=sum(
            item.state == "ENTERPRISE_EXTENSION" for item in items
        ),
    )
