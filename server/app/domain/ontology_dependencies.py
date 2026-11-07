"""发布新本体时冻结资源引用闭包；历史读取不调用本模块。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.status_service import get_revision
from app.models.enums import ResourceStatus
from app.models.resource import ModelResource


def freeze_dependency_versions(
    session: Session, selected: dict[str, int], explicit: dict[str, int]
) -> dict[str, int]:
    pins = dict(selected)
    pending = list(pins)
    visited: set[str] = set()
    while pending:
        key = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        frozen = get_revision(session, int(key), pins[key])
        payload = frozen.payload
        owned = payload.get("owned_versions", {})
        if not isinstance(owned, dict):
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION, {"reason": "invalid_owned_versions"}
            )
        refs = payload.get("resource_refs", [])
        dependencies = set(payload.get("parent_ids", []))
        dependencies.update(ref["target_id"] for ref in refs)
        owned_ids = {
            ref["target_id"]
            for ref in refs
            if ref["role"]
            in {
                "data_prop",
                "assoc_attribute",
                "assoc_resource",
            }
        }
        for target_id in sorted(dependencies):
            target_key = str(target_id)
            pin = owned.get(target_key)
            if target_id in owned_ids and pin is None:
                # Existing snapshots did not record independent child versions.
                # An explicit ontology member pin is allowed, never live guessing.
                pin = explicit.get(target_key)
                if pin is None:
                    raise KGError(
                        ErrorCode.VALIDATION_VIOLATION,
                        {
                            "reason": "missing_owned_version",
                            "resource_id": int(key),
                            "target_id": target_id,
                        },
                    )
            if pin is not None and (type(pin) is not int or pin < 1):
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION, {"reason": "invalid_owned_versions"}
                )
            if target_key in pins:
                if pin is not None and pin != pins[target_key]:
                    raise KGError(
                        ErrorCode.REVISION_CONFLICT,
                        {
                            "resource_id": target_id,
                            "expected": pin,
                            "actual": pins[target_key],
                        },
                    )
                continue
            if pin is None:
                # External type references are resolved at this new ontology's
                # publication boundary, then remain immutable in its revision.
                target = session.get(ModelResource, target_id)
                if target is None or target.status != ResourceStatus.PUBLISHED:
                    raise KGError(
                        ErrorCode.VALIDATION_VIOLATION,
                        {
                            "reason": "dependency_not_published",
                            "resource_id": target_id,
                        },
                    )
                pin = target.current_revision
            pins[target_key] = pin
            pending.append(target_key)
    return pins
