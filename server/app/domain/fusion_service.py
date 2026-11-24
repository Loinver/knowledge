"""Resolve mapped candidates once and freeze evidence in the owning run JSON."""

from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.fusion_policy import canonical_value, resolve_attribute
from app.models.extraction import (
    EntityIdentity,
    ExtractionRun,
    GraphRevision,
    Quarantine,
)


def collect_fusion_row(
    groups: dict[str, dict],
    iri: str,
    em: dict,
    source_id: int,
    row_key: str,
    raw: dict,
    attrs: dict,
    invalid_fields: set[str],
) -> None:
    group = groups.setdefault(
        iri,
        {
            "entity_type": em["entity_type"],
            "policy": em["fusion"],
            "attributes": {},
        },
    )
    for fm in em["field_maps"]:
        attr = fm["target_attr"]
        value = attrs.get(attr)
        state = (
            "INVALID"
            if attr in invalid_fields
            else (
                "SKIPPED"
                if attr not in attrs
                else "NULL"
                if value is None or value == ""
                else "VALUE"
            )
        )
        # Only mapped columns are retained; no complete source row or credentials.
        candidate = {
            "source_id": source_id,
            "schema_name": em.get("schema", "main"),
            "table_name": em["table"],
            "row_key": row_key,
            "column": fm["source_field"],
            "priority": em["fusion"]["priority"],
            "value": value,
            "input_value": raw.get(fm["source_field"]),
            "state": state,
        }
        group["attributes"].setdefault(attr, []).append(
            json.loads(canonical_value(candidate))
        )


def freeze_fusion(
    session: Session,
    run: ExtractionRun,
    gr: GraphRevision,
    groups: dict[str, dict],
    entity_index: dict,
) -> tuple[set[str], int]:
    """Keep quarantined identities indexed during relation extraction to stop stubs."""
    source_identities: dict[tuple, set[str]] = defaultdict(set)
    for iri, group in groups.items():
        for candidates in group["attributes"].values():
            for c in candidates:
                source_identities[
                    (c["source_id"], c["schema_name"], c["table_name"], c["row_key"])
                ].add(iri)
    entities = {
        e.iri: e
        for e in session.scalars(
            select(EntityIdentity).where(EntityIdentity.graph_revision_id == gr.id)
        )
    }
    frozen: dict[str, dict] = {}
    blocked: set[str] = set()
    quarantine_count = 0
    for iri, group in sorted(groups.items()):
        decisions = [
            resolve_attribute(attr, candidates, group["policy"])
            for attr, candidates in sorted(group["attributes"].items())
        ]
        duplicate_identity = any(
            len(
                source_identities[
                    (c["source_id"], c["schema_name"], c["table_name"], c["row_key"])
                ]
            )
            > 1
            for d in decisions
            for c in d["candidates"]
        )
        if duplicate_identity:
            for decision in decisions:
                decision.update(
                    state="QUARANTINED",
                    reason="DUPLICATE_SOURCE_CONFLICT",
                    conflict=True,
                )
        quarantined = any(d["state"] == "QUARANTINED" for d in decisions)
        if quarantined:
            blocked.add(iri)
            entity_index[iri]["fusion_quarantined"] = True
            for decision in decisions:
                if decision["state"] != "QUARANTINED":
                    decision["reason"] = "ENTITY_QUARANTINED"
                decision.update(
                    state="QUARANTINED", final_value=None, final_value_present=False
                )
                seen_rows: set[tuple[str, str]] = set()
                for c in decision["candidates"]:
                    c["selected"] = False
                    row = (c["table_name"], c["row_key"])
                    if row in seen_rows:
                        continue
                    seen_rows.add(row)
                    session.add(
                        Quarantine(
                            run_id=run.id,
                            table_name=row[0],
                            row_key=row[1],
                            field=decision["attribute"],
                            raw_value=None,
                            transform_chain=["fusion", decision["reason"]],
                            rule_id="fusion_conflict",
                        )
                    )
                    quarantine_count += 1
        entity = entities[iri]
        entity.attrs = {
            d["attribute"]: d["final_value"]
            for d in decisions
            if d["final_value_present"]
        }
        # A stable representative row is display metadata, never a value-selection rule.
        rows = sorted(
            {
                (c["schema_name"], c["table_name"], c["row_key"])
                for d in decisions
                for c in d["candidates"]
            }
        )
        if rows:
            entity.row_key = rows[0][2]
            entity_index[iri].update(table=rows[0][1], row_key=rows[0][2])
        frozen[iri] = {
            "type_iri": entity.type_iri,
            "state": "QUARANTINED" if quarantined else "RESOLVED",
            "attributes": decisions,
        }
    if groups:
        run.cfg_snapshot = {
            **run.cfg_snapshot,
            "fusion_evidence": {"version": 1, "entities": frozen},
        }
    session.flush()
    return blocked, quarantine_count


def frozen_fusion_entity(run: ExtractionRun | None, iri: str) -> dict | None:
    if run is None:
        return None
    evidence = run.cfg_snapshot.get("fusion_evidence")
    if not isinstance(evidence, dict) or evidence.get("version") != 1:
        return None
    entity = evidence.get("entities", {}).get(iri)
    return entity if isinstance(entity, dict) else None
