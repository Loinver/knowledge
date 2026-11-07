"""Mapping policy validation and deterministic attribute selection, without IO."""

from __future__ import annotations

import json
from collections import defaultdict

from pydantic import ValidationError

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.schemas.mapping import FusionPolicy


def validate_fusion_policies(entity_maps: list[dict]) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for em in entity_maps:
        groups[em["entity_type"]].append(em)
    for entity_type, maps in groups.items():
        if not any(em.get("match_keys") for em in maps):
            continue
        seen: set[tuple[str, str]] = set()
        shared: set[tuple[str, str, int]] = set()
        for em in maps:
            reason = ""
            if not em.get("match_keys"):
                reason = "fusion_mixed_identity"
            elif not em.get("fusion"):
                reason = "fusion_policy_required"
            elif not em.get("key_fields"):
                reason = "fusion_stable_row_key_required"
            source = (em.get("schema", "main"), em.get("table", ""))
            if source in seen:
                reason = "fusion_duplicate_source_mapping"
            seen.add(source)
            if reason:
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION,
                    {
                        "reason": reason,
                        "entity_type": entity_type,
                        "table": em["table"],
                    },
                )
            try:
                policy = FusionPolicy.model_validate(em["fusion"])
            except ValidationError:
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION,
                    {"reason": "fusion_invalid_policy", "entity_type": entity_type},
                ) from None
            shared.add(
                (policy.null_policy, policy.conflict_policy, len(em["match_keys"]))
            )
        if len(shared) != 1:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"reason": "fusion_inconsistent_policy", "entity_type": entity_type},
            )


def canonical_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def resolve_attribute(attribute: str, candidates: list[dict], policy: dict) -> dict:
    """Duplicate rows do not vote; conflicting repeated identities quarantine."""
    unique: dict[str, dict] = {}
    source_values: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        item = dict(candidate)
        source_key = canonical_value(
            [
                item["source_id"],
                item["schema_name"],
                item["table_name"],
                item["row_key"],
                item["column"],
            ]
        )
        value_key = canonical_value([item["state"], item["value"]])
        source_values[source_key].add(value_key)
        # Distinct raw inputs may normalize to one value; retain both explanations.
        key = canonical_value([source_key, value_key, item["input_value"]])
        if key in unique:
            unique[key]["occurrences"] += 1
        else:
            unique[key] = {**item, "occurrences": 1, "selected": False}
    ordered = [unique[key] for key in sorted(unique)]
    eligible = [
        c
        for c in ordered
        if c["state"] == "VALUE"
        or (c["state"] == "NULL" and policy["null_policy"] == "KEEP")
    ]
    distinct = {canonical_value(c["value"]) for c in eligible}
    reason = "NO_VALUE"
    chosen: list[dict] = []
    quarantined = False
    if any(len(values) > 1 for values in source_values.values()):
        reason, quarantined = "DUPLICATE_SOURCE_CONFLICT", True
    elif any(c["state"] == "INVALID" for c in ordered):
        reason, quarantined = "INVALID_SOURCE", True
    elif not eligible:
        reason = (
            "ALL_NULL" if all(c["state"] == "NULL" for c in ordered) else "NO_VALUE"
        )
    elif len(distinct) == 1:
        chosen = eligible
        reason = "AGREEMENT" if len(eligible) > 1 else "SINGLE_VALUE"
    elif policy["conflict_policy"] == "QUARANTINE":
        reason, quarantined = "CONFLICT_QUARANTINED", True
    else:
        rank = min(c["priority"] for c in eligible)
        top = [c for c in eligible if c["priority"] == rank]
        if len({canonical_value(c["value"]) for c in top}) > 1:
            reason, quarantined = "PRIORITY_TIE", True
        else:
            chosen, reason = top, "SOURCE_PRIORITY"
    for item in ordered:
        item["selected"] = item in chosen
    return {
        "attribute": attribute,
        "reason": reason,
        "conflict": len(distinct) > 1 or quarantined,
        "state": "QUARANTINED" if quarantined else "RESOLVED",
        "final_value_present": bool(chosen),
        "final_value": chosen[0]["value"] if chosen else None,
        "null_policy": policy["null_policy"],
        "conflict_policy": policy["conflict_policy"],
        "candidates": ordered,
    }
