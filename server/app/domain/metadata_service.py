"""元数据采集与目录服务（H-21）。

流程：连接数据源 → 采 schema/表/字段 → 结构快照存 metadata_snapshot →
与上一版 diff（表级 + 字段级 added/removed/modified）。
凭据不出现在 catalog。反向引用：扫 mapping_revision 的 entity_maps/rel_maps。
"""

from __future__ import annotations

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine, Inspector
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.source_service import _build_engine, get_datasource
from app.models.data_access import Mapping, MappingRevision, MetadataSnapshot


def _collect_catalog(engine: Engine, kind: str) -> dict:
    """采集 schema -> tables -> columns 结构。SQLite 无 schema 归 main。"""
    insp = inspect(engine)
    schemas_data: list[dict] = []
    table_count = 0
    column_count = 0
    schema_list = insp.get_schema_names()
    if kind == "sqlite" or not schema_list:
        schema_list = ["main"]
    for schema_name in schema_list:
        if kind != "sqlite" and schema_name in ("information_schema",):
            continue
        tables_data: list[dict] = []
        table_names = insp.get_table_names(schema=schema_name)
        view_names = insp.get_view_names(schema=schema_name)
        for tname in table_names:
            cols = _collect_columns(insp, tname, schema_name)
            tables_data.append({"name": tname, "type": "table", "columns": cols})
            table_count += 1
            column_count += len(cols)
        for vname in view_names:
            cols = _collect_columns(insp, vname, schema_name)
            tables_data.append({"name": vname, "type": "view", "columns": cols})
            table_count += 1
            column_count += len(cols)
        schemas_data.append({"schema": schema_name, "tables": tables_data})
    return {
        "schemas": schemas_data,
        "table_count": table_count,
        "column_count": column_count,
    }


def _collect_columns(insp: Inspector, table_name: str, schema_name: str) -> list[dict]:
    cols: list[dict] = []
    pk_names: list[str] = (
        insp.get_pk_constraint(table_name, schema=schema_name).get(
            "constraint_column_names", []
        )
        or []
    )
    pk_cols = set(pk_names)
    fks = _collect_foreign_keys(insp, table_name, schema_name)
    for col in insp.get_columns(table_name, schema=schema_name) or []:
        fk_str = fks.get(col["name"])
        cols.append(
            {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": bool(col.get("nullable", True)),
                "primary_key": col["name"] in pk_cols,
                "foreign_key": fk_str,
            }
        )
    return cols


def _collect_foreign_keys(
    insp: Inspector, table_name: str, schema_name: str
) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for fk in insp.get_foreign_keys(table_name, schema=schema_name) or []:
        cols = fk.get("constrained_columns") or []
        ref_table = fk.get("referred_table", "")
        ref_cols = fk.get("referred_columns") or []
        for i, col in enumerate(cols):
            ref_col = ref_cols[i] if i < len(ref_cols) else ""
            result[col] = f"{ref_table}.{ref_col}" if ref_table else None
    return result


def _next_revision(session: Session, ds_id: int) -> int:
    latest = (
        session.execute(
            select(MetadataSnapshot)
            .where(MetadataSnapshot.datasource_id == ds_id)
            .order_by(MetadataSnapshot.revision.desc())
        )
        .scalars()
        .first()
    )
    return (latest.revision + 1) if latest else 1


def _get_latest_snapshot(session: Session, ds_id: int) -> MetadataSnapshot | None:
    return (
        session.execute(
            select(MetadataSnapshot)
            .where(MetadataSnapshot.datasource_id == ds_id)
            .order_by(MetadataSnapshot.revision.desc())
        )
        .scalars()
        .first()
    )


def capture_metadata(session: Session, ds_id: int) -> MetadataSnapshot:
    """采集元数据并存快照。失败抛 SOURCE_UNREACHABLE。"""
    ds = get_datasource(session, ds_id)
    try:
        engine = _build_engine(ds)
    except Exception as e:
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE,
            {"datasource_id": ds_id, "reason": str(e)[:200]},
        ) from e
    try:
        catalog = _collect_catalog(engine, ds.kind)
    except Exception as e:
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE,
            {"datasource_id": ds_id, "reason": str(e)[:200]},
        ) from e

    revision = _next_revision(session, ds_id)
    prev = _get_latest_snapshot(session, ds_id)
    diff = _build_diff(prev.catalog if prev else None, catalog) if prev else None

    snap = MetadataSnapshot(
        datasource_id=ds_id,
        revision=revision,
        catalog=catalog,
        diff=diff,
    )
    session.add(snap)
    session.flush()
    return snap


def _build_diff(prev_catalog: dict | None, curr_catalog: dict) -> dict:
    """表级 + 字段级 added/removed/modified。"""
    prev_tables = _index_tables(prev_catalog or {"schemas": []})
    curr_tables = _index_tables(curr_catalog)
    table_diffs: list[dict] = []
    column_diffs: list[dict] = []
    all_keys = set(prev_tables.keys()) | set(curr_tables.keys())
    for key in all_keys:
        p = prev_tables.get(key)
        c = curr_tables.get(key)
        schema, tname = key.split(":", 1) if ":" in key else ("main", key)
        if p is None and c is not None:
            table_diffs.append({"name": tname, "type": "added", "schema": schema})
            for col in c.get("columns", []):
                column_diffs.append(
                    {
                        "table": tname,
                        "schema": schema,
                        "column": col["name"],
                        "type": "added",
                    }
                )
        elif p is not None and c is None:
            table_diffs.append({"name": tname, "type": "removed", "schema": schema})
            for col in p.get("columns", []):
                column_diffs.append(
                    {
                        "table": tname,
                        "schema": schema,
                        "column": col["name"],
                        "type": "removed",
                    }
                )
        elif p is not None and c is not None:
            column_diffs.extend(
                _diff_columns(schema, tname, p["columns"], c["columns"])
            )
    summary = {
        "tables_added": sum(1 for d in table_diffs if d["type"] == "added"),
        "tables_removed": sum(1 for d in table_diffs if d["type"] == "removed"),
        "columns_added": sum(1 for d in column_diffs if d["type"] == "added"),
        "columns_removed": sum(1 for d in column_diffs if d["type"] == "removed"),
        "columns_modified": sum(1 for d in column_diffs if d["type"] == "modified"),
    }
    return {"tables": table_diffs, "columns": column_diffs, "summary": summary}


def _index_tables(catalog: dict) -> dict[str, dict]:
    """schema:table -> table dict。"""
    result: dict[str, dict] = {}
    for schema_info in catalog.get("schemas", []):
        sname = schema_info.get("schema", "main")
        for table in schema_info.get("tables", []):
            result[f"{sname}:{table['name']}"] = table
    return result


def _diff_columns(
    schema: str, table: str, prev: list[dict], curr: list[dict]
) -> list[dict]:
    prev_map = {c["name"]: c for c in prev}
    curr_map = {c["name"]: c for c in curr}
    diffs: list[dict] = []
    for name in set(prev_map.keys()) | set(curr_map.keys()):
        p = prev_map.get(name)
        c = curr_map.get(name)
        if p is None and c is not None:
            diffs.append(
                {"table": table, "schema": schema, "column": name, "type": "added"}
            )
        elif p is not None and c is None:
            diffs.append(
                {"table": table, "schema": schema, "column": name, "type": "removed"}
            )
        elif (
            p is not None
            and c is not None
            and (
                p.get("type") != c.get("type") or p.get("nullable") != c.get("nullable")
            )
        ):
            details = f"{p.get('type')} -> {c.get('type')}"
            diffs.append(
                {
                    "table": table,
                    "schema": schema,
                    "column": name,
                    "type": "modified",
                    "details": details,
                }
            )
    return diffs


def list_snapshots(
    session: Session, ds_id: int, page: int = 1, page_size: int = 50
) -> tuple[list[MetadataSnapshot], int]:
    stmt = (
        select(MetadataSnapshot)
        .where(MetadataSnapshot.datasource_id == ds_id)
        .order_by(MetadataSnapshot.revision.desc())
    )
    count_stmt = select(MetadataSnapshot).where(MetadataSnapshot.datasource_id == ds_id)
    total = len(list(session.execute(count_stmt).scalars()))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = list(session.execute(stmt).scalars())
    return items, total


def get_snapshot(session: Session, snapshot_id: int) -> MetadataSnapshot:
    snap = session.get(MetadataSnapshot, snapshot_id)
    if snap is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"snapshot_id": snapshot_id})
    return snap


def get_latest_snapshot(session: Session, ds_id: int) -> MetadataSnapshot | None:
    return _get_latest_snapshot(session, ds_id)


def find_table_references(session: Session, table_name: str) -> list[dict]:
    """反向引用：扫 mapping_revision 的 entity_maps/rel_maps 引用了该表。"""
    refs: list[dict] = []
    seen: set[tuple[int, str]] = set()
    revisions = list(session.execute(select(MappingRevision)).scalars())
    mappings = {m.id: m for m in session.execute(select(Mapping)).scalars()}
    for rev in revisions:
        for em in rev.entity_maps or []:
            if em.get("table") == table_name:
                key = (rev.mapping_id, "entity")
                if key not in seen:
                    m = mappings.get(rev.mapping_id)
                    refs.append(
                        {
                            "mapping_id": rev.mapping_id,
                            "mapping_name": m.name
                            if m
                            else f"mapping-{rev.mapping_id}",
                            "role": "entity",
                        }
                    )
                    seen.add(key)
        for rm in rev.rel_maps or []:
            for side in ("source", "target"):
                spec = rm.get(side)
                if isinstance(spec, dict) and spec.get("table") == table_name:
                    key = (rev.mapping_id, "relation")
                    if key not in seen:
                        m = mappings.get(rev.mapping_id)
                        refs.append(
                            {
                                "mapping_id": rev.mapping_id,
                                "mapping_name": m.name
                                if m
                                else f"mapping-{rev.mapping_id}",
                                "role": "relation",
                            }
                        )
                        seen.add(key)
    return refs
