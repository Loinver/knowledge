"""Authorized context with server handles and reproducible fingerprints."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_dependencies import freeze_dependency_versions
from app.domain.ontology_validation_context import working_context
from app.domain.status_service import get_revision
from app.models.domain import Ontology
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import ModelResource, Namespace
from app.schemas.ontology_modeling import PROFILE_VERSION, ModelingCreate

_KINDS = {
    ResourceKind.ENTITY: "CLASS",
    ResourceKind.ASSOC: "CLASS",
    ResourceKind.DATATYPE_PROP: "DATA_PROPERTY",
    ResourceKind.OBJECT_PROP: "OBJECT_PROPERTY",
}
MAX_CATALOG = 200


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def prepare_context(
    session: Session, request: ModelingCreate, *, token: str | None = None
) -> dict:
    if request.profile != "BUSINESS" or request.profile_version != PROFILE_VERSION:
        raise KGError(
            ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED,
            {"reason": "core_profile_not_approved"},
        )
    onto = session.get(Ontology, request.target_ontology_id, populate_existing=True)
    if onto is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": request.target_ontology_id}
        )
    draft_id = f"ontology:{onto.id}:working"
    if (
        request.target_draft_id != draft_id
        or request.base_edit_revision != onto.edit_revision
        or onto.status == ResourceStatus.ARCHIVED
    ):
        raise KGError(ErrorCode.ONTOLOGY_PROPOSAL_STALE, {"reason": "draft_changed"})
    fixed = working_context(session, onto)
    namespaces = {}
    for namespace_id in sorted(set(request.namespace_ids)):
        ns = session.get(Namespace, namespace_id, populate_existing=True)
        if ns is None or ns.protected:
            raise KGError(ErrorCode.INVALID_NAMESPACE, {"namespace_id": namespace_id})
        namespaces[f"ns:{ns.id}"] = {
            "id": ns.id,
            "iri": ns.iri,
            "prefix": ns.prefix,
            "protected": ns.protected,
        }
    # Name inventory is never sent as material. It detects new duplicates even
    # when a new resource was not part of the original bounded retrieval set.
    inventory = list(
        session.execute(
            select(ModelResource.id, ModelResource.name, ModelResource.iri).order_by(
                ModelResource.id
            )
        ).tuples()
    )
    selected = set(request.asset_ids) | set(fixed.payloads)
    concepts = []
    material = "\n".join(
        [request.text, *(excerpt.text for excerpt in request.excerpts)]
    ).casefold()
    for rid, kind, labels, aliases in session.execute(
        select(
            ModelResource.id,
            ModelResource.kind,
            ModelResource.label_i18n,
            ModelResource.synonyms,
        ).order_by(ModelResource.id)
    ):
        words = [
            (language, text)
            for language, text in (labels or {}).items()
            if isinstance(text, str)
        ]
        words.extend((alias["language"], alias["text"]) for alias in (aliases or []))
        concepts.append(
            {
                "id": rid,
                "kind": _KINDS.get(kind),
                "words": [list(word) for word in words],
            }
        )
        if any(
            text.strip() and text.casefold() in material for _language, text in words
        ):
            selected.add(rid)
    for rid, name, _iri in inventory:
        if name.casefold() in material:
            selected.add(rid)
    selected_pins = {}
    for rid in selected:
        resource = session.get(ModelResource, rid, populate_existing=True)
        if resource is not None and resource.current_revision > 0:
            selected_pins[str(rid)] = (
                fixed.resolved_versions.get(rid) or resource.current_revision
            )
    if selected_pins:
        selected_pins = freeze_dependency_versions(
            session, selected_pins, selected_pins
        )
        selected.update(int(rid) for rid in selected_pins)
    if len(selected) > MAX_CATALOG:
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"reason": "modeling_context_too_large", "max": MAX_CATALOG},
        )
    catalog: dict[str, dict] = {}
    sources: dict[str, dict[str, str]] = {}
    source_details: dict[str, dict] = {}

    def source(handle: str, title: str, text: str) -> None:
        spans = {
            f"span:{i}": line
            for i, line in enumerate(text.splitlines(), 1)
            if line.strip()
        }
        if not spans:
            spans = {"span:1": text}
        sources[handle] = spans
        source_details[handle] = {
            "title": title,
            "content_hash": digest(text),
            "spans": [
                {"handle": key, "line": int(key.split(":")[1]), "text": value}
                for key, value in spans.items()
            ],
        }

    source("source:request", "USER_REQUEST", request.text)
    for index, excerpt in enumerate(request.excerpts, 1):
        source(f"source:excerpt:{index}", excerpt.title, excerpt.text)
    for rid in sorted(selected):
        resource = session.get(ModelResource, rid, populate_existing=True)
        if resource is None:
            raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"resource_id": rid})
        if resource.kind not in _KINDS or resource.current_revision < 1:
            if rid in request.asset_ids:
                raise KGError(
                    ErrorCode.INVALID_REQUEST,
                    {"reason": "reuse_requires_published_revision", "resource_id": rid},
                )
            continue
        # Reuse current ontology pins where present; otherwise freeze latest
        # published payload, never a mutable draft with a published identity.
        payload = fixed.payloads.get(rid)
        pin = selected_pins[str(rid)]
        if payload is not None:
            # Exact pinned revisions are recorded in the context projection.
            pin = fixed.resolved_versions.get(rid) or pin
        frozen = get_revision(session, rid, pin)
        payload = deepcopy(frozen.payload)
        metadata = {
            "labels": payload.get("label_i18n") or {},
            "definitions": payload.get("definition_i18n") or {},
            "synonyms": payload.get("synonyms") or [],
        }
        handle = f"asset:{rid}:{pin}"
        catalog[handle] = {
            "id": rid,
            "revision": pin,
            "kind": _KINDS[ResourceKind(payload["kind"])],
            "iri": payload["iri"],
            "name": payload["name"],
            "metadata": metadata,
            "namespace_id": resource.namespace_id,
            "snapshot": payload,
            "checksum": frozen.checksum,
            "status": "PUBLISHED",
        }
        source(
            f"source:{handle}",
            payload["name"],
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        )
    iri_by_id = {asset["id"]: asset["iri"] for asset in catalog.values()}
    for asset in catalog.values():
        snapshot = asset["snapshot"]
        asset["parents"] = [
            iri_by_id[rid] for rid in snapshot.get("parent_ids", []) if rid in iri_by_id
        ]
        detail = snapshot.get("object_prop") or {}
        for key, role in (
            ("domain", "relation_domain"),
            ("range", "relation_range"),
            ("inverse", "inverse_of"),
        ):
            match = next(
                (
                    ref["target_id"]
                    for ref in snapshot.get("resource_refs", [])
                    if ref["role"] == role
                ),
                None,
            )
            if match in iri_by_id:
                asset[key + "_iri"] = iri_by_id[match]
        asset["features"] = detail.get("owl") or {}
        props = snapshot.get("datatype_props") or []
        if asset["kind"] == "DATA_PROPERTY" and props:
            asset["datatype"] = props[0]["datatype"]
        if asset["kind"] == "CLASS":
            for ref in snapshot.get("resource_refs", []):
                if ref["role"] in {"data_prop", "assoc_attribute"}:
                    for child in catalog.values():
                        if child["id"] == ref["target_id"]:
                            child["owner_iri"] = asset["iri"]
    context = {
        "ontology_id": onto.id,
        "target_draft_id": draft_id,
        "base_edit_revision": onto.edit_revision,
        "published_revision": onto.current_revision,
        "working_digest": fixed.digest,
        "working_payloads": {str(rid): value for rid, value in fixed.payloads.items()},
        "working_rules": fixed.rules,
        "inventory": [list(row) for row in inventory],
        "concept_inventory": concepts,
        "inventory_digest": digest([list(row) for row in inventory]),
        "profile": request.profile,
        "profile_version": request.profile_version,
        "namespace_catalog": namespaces,
        "asset_catalog": catalog,
        "source_catalog": sources,
        "source_details": source_details,
        "request": request.model_dump(mode="json"),
        "ontology_metadata": fixed.metadata,
    }
    context["fingerprint"] = digest(context)
    context["context_token"] = token or uuid4().hex
    return context


def assert_context_current(session: Session, context: dict) -> None:
    rebuilt = prepare_context(
        session,
        ModelingCreate.model_validate(context["request"]),
        token=context["context_token"],
    )
    if rebuilt["fingerprint"] != context["fingerprint"]:
        raise KGError(ErrorCode.ONTOLOGY_PROPOSAL_STALE, {"reason": "context_changed"})
