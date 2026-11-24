"""只读取冻结修订；成员和 pin 不回退到当前本体、资源或规则。"""

from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_snapshot import load_resource_snapshot
from app.domain.status_service import get_revision
from app.models.domain import OntologyRevision
from app.schemas.ontology_history import (
    HistoryResourceSnapshot,
    HistorySnapshotState,
    OntologyHistoryResourceBrief,
    OntologyHistoryResourceOut,
    OntologyHistoryRuleBrief,
    OntologyHistoryRuleOut,
    OntologyRevisionContents,
)


def _revision(session: Session, ontology_id: int, revision: int) -> OntologyRevision:
    frozen = session.scalar(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == ontology_id,
            OntologyRevision.revision == revision,
        )
    )
    if frozen is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {"ontology_id": ontology_id, "revision": revision},
        )
    return frozen


def _invalid(frozen: OntologyRevision, reason: str) -> KGError:
    return KGError(
        ErrorCode.VALIDATION_VIOLATION,
        {
            "ontology_id": frozen.ontology_id,
            "revision": frozen.revision,
            "reason": reason,
        },
    )


def _resource_versions(frozen: OntologyRevision) -> dict[int, int]:
    if not isinstance(frozen.resource_versions, dict):
        raise _invalid(frozen, "invalid_resource_versions")
    pins: dict[int, int] = {}
    for key, pin in frozen.resource_versions.items():
        try:
            resource_id = int(key)
        except (TypeError, ValueError) as exc:
            raise _invalid(frozen, "invalid_resource_versions") from exc
        if (
            resource_id < 1
            or str(resource_id) != key
            or type(pin) is not int
            or pin < 1
        ):
            raise _invalid(frozen, "invalid_resource_versions")
        pins[resource_id] = pin
    return pins


def _resource(
    session: Session, frozen: OntologyRevision, resource_id: int, pin: int
) -> OntologyHistoryResourceOut:
    # Retain the existing completeness/enum checks, then read the full payload
    # so display-only fields such as default_value and labels survive.
    validated = load_resource_snapshot(session, resource_id, pin)
    history = get_revision(session, resource_id, pin)
    try:
        snapshot = HistoryResourceSnapshot.model_validate(
            {**history.payload, "id": resource_id, "owl": validated.owl}
        )
    except ValidationError as exc:
        raise _invalid(frozen, "invalid_snapshot_structure") from exc
    return OntologyHistoryResourceOut(
        ontology_id=frozen.ontology_id,
        ontology_revision=frozen.revision,
        resource_id=resource_id,
        revision=pin,
        checksum=history.checksum,
        published_at=history.published_at,
        snapshot=snapshot,
    )


def _rules(frozen: OntologyRevision) -> list[OntologyHistoryRuleOut]:
    if not isinstance(frozen.rules, list):
        raise _invalid(frozen, "invalid_rule_snapshot")
    result: list[OntologyHistoryRuleOut] = []
    seen: set[int] = set()
    for item in frozen.rules:
        if not isinstance(item, dict):
            raise _invalid(frozen, "invalid_rule_snapshot")
        try:
            rule = OntologyHistoryRuleOut.model_validate(
                {
                    **item,
                    "ontology_id": frozen.ontology_id,
                    "ontology_revision": frozen.revision,
                    "snapshot_state": HistorySnapshotState.AVAILABLE
                    if item.get("snapshot") is not None
                    else HistorySnapshotState.UNAVAILABLE,
                }
            )
        except (ValidationError, KGError) as exc:
            raise _invalid(frozen, "invalid_rule_snapshot") from exc
        if rule.rule_id in seen:
            raise _invalid(frozen, "invalid_rule_snapshot")
        seen.add(rule.rule_id)
        snapshot = rule.snapshot
        if snapshot is not None and (
            snapshot.id != rule.rule_id
            or snapshot.revision != rule.revision
            or snapshot.identifier != rule.identifier
            or snapshot.source_kind != rule.source_kind
            or snapshot.source_reference != rule.source_reference
        ):
            raise _invalid(frozen, "invalid_rule_snapshot")
        result.append(rule)
    return sorted(result, key=lambda rule: rule.rule_id)


def get_revision_contents(
    session: Session, ontology_id: int, revision: int
) -> OntologyRevisionContents:
    with session.no_autoflush:
        frozen = _revision(session, ontology_id, revision)
        resources = []
        for resource_id, pin in sorted(_resource_versions(frozen).items()):
            detail = _resource(session, frozen, resource_id, pin)
            resources.append(
                OntologyHistoryResourceBrief(
                    resource_id=resource_id,
                    revision=pin,
                    name=detail.snapshot.name,
                    iri=detail.snapshot.iri,
                    kind=detail.snapshot.kind,
                    label_i18n=detail.snapshot.label_i18n,
                )
            )
        return OntologyRevisionContents(
            ontology_id=ontology_id,
            revision=revision,
            published_at=frozen.published_at,
            resources=resources,
            rules=[
                OntologyHistoryRuleBrief.model_validate(rule.model_dump())
                for rule in _rules(frozen)
            ],
        )


def get_revision_resource(
    session: Session, ontology_id: int, revision: int, resource_id: int
) -> OntologyHistoryResourceOut:
    with session.no_autoflush:
        frozen = _revision(session, ontology_id, revision)
        pin = _resource_versions(frozen).get(resource_id)
        if pin is None:
            raise KGError(
                ErrorCode.RESOURCE_NOT_FOUND,
                {
                    "ontology_id": ontology_id,
                    "revision": revision,
                    "resource_id": resource_id,
                },
            )
        return _resource(session, frozen, resource_id, pin)


def get_revision_rule(
    session: Session, ontology_id: int, revision: int, rule_id: int
) -> OntologyHistoryRuleOut:
    with session.no_autoflush:
        frozen = _revision(session, ontology_id, revision)
        for rule in _rules(frozen):
            if rule.rule_id == rule_id:
                return rule
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"ontology_id": ontology_id, "revision": revision, "rule_id": rule_id},
        )
