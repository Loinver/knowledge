"""资产校验的固定输入；工作草稿与发布快照不混用。"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_snapshot import ResourceSnapshot, load_resource_snapshot
from app.domain.resource_payload import build_resource_payload
from app.domain.status_service import get_revision
from app.domain.template_service import get_template, lock_template, template_resources
from app.models.domain import (
    Ontology,
    OntologyResourceRef,
    OntologyRevision,
    OntologyRuleRef,
)
from app.models.enums import ResourceStatus
from app.models.governance import Rule
from app.models.resource import ModelResource
from app.schemas.governance import RuleOut
from app.schemas.validation import OntologyValidationTarget


@dataclass(frozen=True)
class OntologyValidationContext:
    target: OntologyValidationTarget
    ontology_id: int
    published_revision: int
    edit_revision: int | None
    metadata: dict[str, Any]
    payloads: dict[int, dict]
    resolved_versions: dict[int, int | None]
    referenced_ids: list[int]
    rules: list[dict]
    template: dict | None

    @property
    def digest(self) -> str:
        content = {
            "metadata": self.metadata,
            "resources": self.payloads,
            "versions": self.resolved_versions,
            "members": sorted(self.referenced_ids),
            "rules": self.rules,
            "template": self.template,
        }
        raw = json.dumps(
            content, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def resources(self) -> list[ResourceSnapshot]:
        return [
            ResourceSnapshot.model_validate({**payload, "id": rid})
            for rid, payload in self.payloads.items()
        ]

    def binding(self) -> dict:
        return {
            "target": self.target.value,
            "working_draft_id": f"ontology:{self.ontology_id}:working"
            if self.target == OntologyValidationTarget.WORKING
            else None,
            "edit_revision": self.edit_revision,
            "published_revision": self.published_revision,
            "content_digest": self.digest,
            "checker_version": "ontology-validation/2",
        }


def template_snapshot(session: Session, onto: Ontology, *, lock: bool = False) -> dict:
    if onto.template_id is None:
        return {"template_id": None, "resources": []}
    template = (
        lock_template(session, onto.template_id)
        if lock
        else get_template(session, onto.template_id)
    )
    return {
        "template_id": template.id,
        "revision": template.revision,
        "resources": [
            member.model_dump(mode="json") for member in template_resources(template)
        ],
    }


def frozen_context(
    session: Session, onto: Ontology, revision: OntologyRevision
) -> OntologyValidationContext:
    payloads = {}
    for key, pin in revision.resource_versions.items():
        rid = int(key)
        load_resource_snapshot(session, rid, pin)
        payloads[rid] = deepcopy(get_revision(session, rid, pin).payload)
    metadata = deepcopy(revision.metadata_snapshot)
    governance = metadata.pop("governance", {})
    return OntologyValidationContext(
        target=OntologyValidationTarget.PUBLISHED,
        ontology_id=onto.id,
        published_revision=revision.revision,
        edit_revision=None,
        metadata=metadata,
        payloads=payloads,
        resolved_versions={
            int(key): value for key, value in revision.resource_versions.items()
        },
        referenced_ids=revision.ref_domains + revision.ref_types,
        rules=deepcopy(revision.rules),
        # A legacy snapshot cannot prove it had no template. The live ontology
        # may have changed its template since this historical revision.
        template=governance.get("template"),
    )


def _working_payloads(
    session: Session, roots: dict[int, int | None]
) -> tuple[dict[int, dict], dict[int, int | None]]:
    """Resolve owned pins to a fixed point, discarding provisional expansions.

    Requirements belong to the payload that supplied them. Expanding a latest
    revision before discovering an owner's historical pin must not turn that
    provisional payload's dependencies into permanent requirements.
    """
    explicit = {rid: pin for rid, pin in roots.items() if pin is not None}
    required = dict(explicit)
    seen: set[tuple[tuple[int, int], ...]] = set()
    for _round in range(256):
        signature = tuple(sorted(required.items()))
        if signature in seen:
            break
        seen.add(signature)
        payloads: dict[int, dict] = {}
        resolved: dict[int, int | None] = {}
        demands: dict[int, set[int]] = {}
        pending = list(roots)
        while pending:
            rid = pending.pop(0)
            if rid in payloads:
                continue
            resource = session.get(ModelResource, rid, populate_existing=True)
            if resource is None:
                continue
            pin = required.get(rid)
            if pin is None and resource.status == ResourceStatus.PUBLISHED:
                pin = resource.current_revision
            if pin is not None:
                load_resource_snapshot(session, rid, pin)
                payload = deepcopy(get_revision(session, rid, pin).payload)
            else:
                payload = build_resource_payload(session, resource)
            payloads[rid], resolved[rid] = payload, pin
            owned = payload.get("owned_versions", {})
            if not isinstance(owned, dict):
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION, {"reason": "invalid_owned_versions"}
                )
            dependencies = set(payload.get("parent_ids", []))
            dependencies.update(
                ref["target_id"] for ref in payload.get("resource_refs", [])
            )
            for dependency in sorted(dependencies):
                owned_pin = owned.get(str(dependency))
                if owned_pin is not None:
                    if type(owned_pin) is not int or owned_pin < 1:
                        raise KGError(
                            ErrorCode.VALIDATION_VIOLATION,
                            {"reason": "invalid_owned_versions"},
                        )
                    demands.setdefault(dependency, set()).add(owned_pin)
                pending.append(dependency)
        # A provisional choice only drives the next expansion. Conflicts are
        # judged after all contributing owner payloads use their final versions.
        next_required = {rid: min(pins) for rid, pins in demands.items()}
        next_required.update(explicit)
        if next_required == required:
            for rid, pins in demands.items():
                expected = explicit.get(rid)
                if len(pins) > 1 or (expected is not None and expected not in pins):
                    raise KGError(
                        ErrorCode.REVISION_CONFLICT,
                        {
                            "resource_id": rid,
                            "expected": expected,
                            "required_revisions": sorted(pins),
                        },
                    )
            return payloads, resolved
        required = next_required
    raise KGError(
        ErrorCode.REVISION_CONFLICT, {"reason": "owned_versions_not_converged"}
    )


def working_context(session: Session, onto: Ontology) -> OntologyValidationContext:
    refs = list(
        session.scalars(
            select(OntologyResourceRef)
            .where(OntologyResourceRef.ontology_id == onto.id)
            .order_by(OntologyResourceRef.resource_id)
        )
    )
    roots = {ref.resource_id: ref.pinned_revision for ref in refs}
    payloads, resolved_pins = _working_payloads(session, roots)
    rules = []
    for ref in session.scalars(
        select(OntologyRuleRef)
        .where(OntologyRuleRef.ontology_id == onto.id)
        .order_by(OntologyRuleRef.rule_id)
    ):
        rule = session.get(Rule, ref.rule_id, populate_existing=True)
        rules.append(
            {
                "rule_id": ref.rule_id,
                "revision": ref.pinned_revision,
                "snapshot": RuleOut.model_validate(rule).model_dump(mode="json")
                if rule
                else None,
            }
        )
    return OntologyValidationContext(
        target=OntologyValidationTarget.WORKING,
        ontology_id=onto.id,
        published_revision=onto.current_revision,
        edit_revision=onto.edit_revision,
        metadata={
            "name": onto.name,
            "iri": onto.iri,
            "label_i18n": deepcopy(onto.label_i18n),
            "definition_i18n": deepcopy(onto.definition_i18n),
            "synonyms": deepcopy(onto.synonyms),
        },
        payloads=payloads,
        resolved_versions=resolved_pins,
        referenced_ids=[ref.resource_id for ref in refs],
        rules=rules,
        template=template_snapshot(session, onto),
    )
