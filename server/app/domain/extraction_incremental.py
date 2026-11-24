"""Append-only entity snapshots: validate a base and preserve original evidence."""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.data_access import MappingRevision
from app.models.enums import RunResult
from app.models.extraction import (
    EntityIdentity,
    ExtractionRun,
    FactEvidence,
    GraphRevision,
)


def invalid_incremental(reason: str) -> KGError:
    return KGError(ErrorCode.VALIDATION_VIOLATION, {"reason": reason})


def validate_incremental_mapping(revision: MappingRevision, catalog: dict) -> None:
    """The supported contract is immutable rows with increasing integer watermarks.

    Arbitrary business keys cannot be recovered losslessly from legacy IRIs.
    Reject ambiguous configurations before querying; never silently scan in full.
    """
    tables: dict[str, list[dict]] = {}
    for schema in catalog.get("schemas", []):
        for table in schema.get("tables", []):
            tables.setdefault(table["name"], []).append(
                {**table, "schema": schema["schema"]}
            )
    mappings: dict[str, dict] = {}
    entity_types: set[str] = set()
    for entity in revision.entity_maps:
        if entity["entity_type"] in entity_types:
            raise invalid_incremental("incremental_duplicate_entity_type")
        entity_types.add(entity["entity_type"])
        name = entity.get("table")
        matches = tables.get(name, [])
        if (
            name in mappings
            or len(matches) != 1
            or matches[0]["schema"] != entity.get("schema", "main")
        ):
            raise invalid_incremental("incremental_ambiguous_table")
        columns = {column["name"]: column for column in matches[0]["columns"]}
        keys = entity.get("key_fields") or []
        primary = [
            column["name"] for column in columns.values() if column.get("primary_key")
        ]
        watermark = entity.get("incremental_field")
        if (
            len(keys) != 1
            or keys != primary
            or "INT" not in columns[keys[0]]["type"].upper()
        ):
            raise invalid_incremental("incremental_requires_integer_primary_key")
        if watermark not in columns or "INT" not in columns[watermark]["type"].upper():
            raise invalid_incremental("incremental_requires_integer_watermark")
        if entity.get("match_keys"):
            raise invalid_incremental("incremental_business_keys_unsupported")
        mappings[name] = entity
    if not mappings:
        raise invalid_incremental("incremental_entity_mapping_required")
    for relation in revision.rel_maps:
        if relation.get("mode") != "FK":
            for side in ("source", "target"):
                endpoint = relation.get(side) or {}
                if endpoint.get("via"):
                    raise invalid_incremental("incremental_via_unsupported")
                for candidate in endpoint.get("candidates") or [endpoint]:
                    target_mapping = mappings.get(candidate.get("ref_table"))
                    if (
                        target_mapping is None
                        or candidate.get("ref_field") != target_mapping["key_fields"][0]
                        or (
                            candidate.get("ref_entity_type")
                            and candidate["ref_entity_type"]
                            != target_mapping["entity_type"]
                        )
                    ):
                        raise invalid_incremental(
                            "incremental_endpoint_key_unsupported"
                        )
            continue
        source = mappings.get(relation.get("table"))
        if source is None:
            raise invalid_incremental("incremental_fk_source_unmapped")
        columns = tables[source["table"]][0]["columns"]
        foreign = next(
            (
                column.get("foreign_key")
                for column in columns
                if column["name"] == relation.get("fk_field")
            ),
            None,
        )
        if not foreign or "." not in foreign:
            raise invalid_incremental("incremental_fk_target_unknown")
        target, key = foreign.rsplit(".", 1)
        if target not in mappings or mappings[target]["key_fields"] != [key]:
            raise invalid_incremental("incremental_fk_target_unmapped")


def clone_incremental_base(
    session: Session,
    base_id: int,
    run: ExtractionRun,
    graph: GraphRevision,
    revision: MappingRevision,
    entity_index: dict,
    key_index: dict,
) -> tuple[int, int]:
    base = session.get(GraphRevision, base_id)
    previous = session.get(ExtractionRun, base.run_id) if base is not None else None
    cfg = run.cfg_snapshot
    if (
        base is None
        or not base.publishable
        or previous is None
        or previous.status != RunResult.SUCCESS
        or previous.mapping_revision_id != revision.id
        or any(
            previous.cfg_snapshot.get(key) != cfg.get(key)
            for key in ("datasource_id", "namespace", "onto_version", "pins")
        )
    ):
        raise invalid_incremental("incremental_base_untrusted")
    by_table = {item["table"]: item for item in revision.entity_maps}
    mapped_types = {
        f"{cfg['namespace']}{item['entity_type']}" for item in revision.entity_maps
    }
    evidence = list(
        session.scalars(
            select(FactEvidence).where(
                FactEvidence.graph_revision_id == base_id,
                FactEvidence.evidence_type == "ENTITY",
            )
        )
    )
    by_subject: dict[str, list[FactEvidence]] = {}
    for item in evidence:
        if (
            item.source_id != cfg["datasource_id"]
            or item.table_name not in by_table
            or item.mapping_revision_id != revision.id
            or item.ontology_revision != revision.onto_version
            or (item.resource_revisions or {}) != cfg["pins"]["resource_versions"]
            or (item.rule_revisions or {}) != cfg["pins"]["rule_revisions"]
        ):
            raise invalid_incremental("incremental_base_evidence_incomplete")
        by_subject.setdefault(item.subject, []).append(item)
    evidence_count = 0
    for entity in session.scalars(
        select(EntityIdentity).where(EntityIdentity.graph_revision_id == base_id)
    ):
        sources = by_subject.get(entity.iri, [])
        if not sources:
            if entity.type_iri in mapped_types:
                raise invalid_incremental("incremental_base_evidence_missing")
            continue  # Relation stubs are rebuilt by the full relation stage.
        session.add(
            EntityIdentity(
                graph_revision_id=graph.id,
                iri=entity.iri,
                type_iri=entity.type_iri,
                row_key=entity.row_key,
                attrs=deepcopy(entity.attrs),
            )
        )
        first = sources[0]
        if any(
            item.table_name != first.table_name or item.row_key != first.row_key
            for item in sources
        ):
            raise invalid_incremental("incremental_base_identity_ambiguous")
        entity_index[entity.iri] = {
            "type": by_table[first.table_name]["entity_type"],
            "row_key": entity.row_key,
            "table": first.table_name,
            "attrs": deepcopy(entity.attrs),
        }
        for item in sources:
            key = (item.table_name, item.row_key)
            if key in key_index and key_index[key] != entity.iri:
                raise invalid_incremental("incremental_base_key_ambiguous")
            key_index[key] = entity.iri
            session.add(
                FactEvidence(
                    graph_revision_id=graph.id,
                    **{
                        name: deepcopy(getattr(item, name))
                        for name in (
                            "subject",
                            "predicate",
                            "object_",
                            "source_id",
                            "table_name",
                            "row_key",
                            "columns",
                            "column_transforms",
                            "run_id",
                            "evidence_type",
                            "mapping_revision_id",
                            "ontology_revision",
                            "resource_revisions",
                            "rule_revisions",
                        )
                    },
                )
            )
            evidence_count += 1
    session.flush()
    return len(entity_index), evidence_count
