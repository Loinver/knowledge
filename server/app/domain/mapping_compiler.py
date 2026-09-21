"""映射编译器（H-31）。

对已发布或草稿 revision 做字段四列实算 + 样例预览。
错误定位到字段级（entity_type/attr 或 relation_type/endpoint）。
A11：空键/重复键/缺失端点/多匹配。
A12：日期/枚举/小数/空值按声明策略。
预览结果落 mapping_preview 表。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.mapping_service import (
    get_draft_revision,
    get_mapping,
    get_published_revision,
)
from app.domain.metadata_service import get_latest_snapshot
from app.domain.source_service import _build_engine, get_datasource
from app.models.data_access import MappingPreview


def compile_mapping(
    session: Session,
    mapping_id: int,
    datasource_id: int,
    limit: int = 20,
    use_draft: bool = False,
) -> dict:
    """编译映射预览。use_draft=True 用草稿，否则用已发布 revision。"""
    get_mapping(session, mapping_id)
    if use_draft:
        rev = get_draft_revision(session, mapping_id)
        if rev is None:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"mapping_id": mapping_id, "reason": "no_draft"},
            )
    else:
        rev = get_published_revision(session, mapping_id)

    if limit > 100:
        limit = 100
    if limit < 1:
        limit = 1

    ds = get_datasource(session, datasource_id)
    snap = get_latest_snapshot(session, datasource_id)
    if snap is None:
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"datasource_id": datasource_id, "reason": "no_metadata_snapshot"},
        )
    table_set = _index_catalog_tables(snap.catalog)
    try:
        engine = _build_engine(ds)
    except Exception as e:
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE,
            {"datasource_id": datasource_id, "reason": str(e)[:200]},
        ) from e

    entities_result: list[dict] = []
    relations_result: list[dict] = []
    errors_all: list[dict] = []

    for em in rev.entity_maps:
        compiled, errs = _compile_entity(em, engine, ds.kind, table_set, limit)
        entities_result.append(compiled)
        errors_all.extend(errs)

    for rm in rev.rel_maps:
        compiled, errs = _compile_relation(rm, engine, ds.kind, table_set, limit)
        relations_result.append(compiled)
        errors_all.extend(errs)

    result = {
        "mapping_id": mapping_id,
        "revision": rev.revision,
        "onto_version": rev.onto_version,
        "entities": entities_result,
        "relations": relations_result,
        "summary": {
            "entity_count": len(entities_result),
            "relation_count": len(relations_result),
            "error_count": len(errors_all),
            "sample_limit": limit,
        },
        "errors": errors_all,
    }

    preview = MappingPreview(
        mapping_revision_id=rev.id,
        results={
            "entities": entities_result,
            "relations": relations_result,
            "summary": result["summary"],
        },
        errors=errors_all,
    )
    session.add(preview)
    session.flush()
    result["preview_id"] = preview.id
    return result


def _index_catalog_tables(catalog: dict) -> set[str]:
    """catalog 里的全表名集合（schema:table 或 table）。"""
    tables: set[str] = set()
    for s in catalog.get("schemas", []):
        sname = s.get("schema", "main")
        for t in s.get("tables", []):
            tables.add(f"{sname}:{t['name']}")
            tables.add(t["name"])
    return tables


def _table_in_catalog(table: str, schema: str, table_set: set[str]) -> bool:
    return table in table_set or f"{schema}:{table}" in table_set


def _compile_entity(
    em: dict,
    engine,
    kind: str,
    table_set: set[str],
    limit: int,
) -> tuple[dict, list[dict]]:
    table = em.get("table", "")
    schema = em.get("schema", "main")
    entity_type = em.get("entity_type", "")
    field_maps = em.get("field_maps", [])
    key_fields = em.get("key_fields", [])
    errs: list[dict] = []

    if not _table_in_catalog(table, schema, table_set):
        errs.append(
            {
                "entity_type": entity_type,
                "table": table,
                "level": "table",
                "code": "table_not_found",
                "message": f"table {table} not in catalog",
            }
        )
        return {
            "entity_type": entity_type,
            "table": table,
            "rows": [],
            "errors": errs,
        }, errs

    qualified = f'"{schema}"."{table}"' if schema and schema != "main" else f'"{table}"'
    sql = text(f"SELECT * FROM {qualified} LIMIT :lim")
    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"lim": limit})
            raw_rows = [dict(r._mapping) for r in result.fetchmany(limit)]
    except Exception as e:
        errs.append(
            {
                "entity_type": entity_type,
                "table": table,
                "level": "table",
                "code": "query_failed",
                "message": str(e)[:200],
            }
        )
        return {
            "entity_type": entity_type,
            "table": table,
            "rows": [],
            "errors": errs,
        }, errs

    compiled_rows: list[dict] = []
    seen_keys: dict[str, int] = {}
    for idx, raw in enumerate(raw_rows):
        cells: list[dict] = []
        row_errs: list[dict] = []
        for fm in field_maps:
            cell, cell_errs = _compile_field(fm, raw, entity_type, idx)
            cells.append(cell)
            row_errs.extend(cell_errs)
        key_parts = []
        for kf in key_fields:
            v = raw.get(kf)
            if v is None or v == "":
                errs.append(
                    {
                        "entity_type": entity_type,
                        "table": table,
                        "row": idx,
                        "field": kf,
                        "level": "field",
                        "code": "empty_key",
                        "message": f"key field {kf} empty at row {idx}",
                    }
                )
            key_parts.append(str(v) if v is not None else "")
        key_str = "|".join(key_parts) if key_parts else None
        if key_str:
            if key_str in seen_keys:
                errs.append(
                    {
                        "entity_type": entity_type,
                        "table": table,
                        "row": idx,
                        "level": "row",
                        "code": "duplicate_key",
                        "message": (
                            f"duplicate key {key_str} "
                            f"(row {idx} == row {seen_keys[key_str]})"
                        ),
                    }
                )
            else:
                seen_keys[key_str] = idx
        compiled_rows.append({"row_index": idx, "source_key": key_str, "cells": cells})
        errs.extend(row_errs)
    return {
        "entity_type": entity_type,
        "table": table,
        "rows": compiled_rows,
        "errors": errs,
    }, errs


def _compile_field(
    fm: dict, raw: dict, entity_type: str, row_idx: int
) -> tuple[dict, list[dict]]:
    target = fm.get("target_attr", "")
    source = fm.get("source_field", "")
    transform = fm.get("transform", "IDENTITY")
    transform_params = fm.get("transform_params") or {}
    null_policy = fm.get("null_policy", "NULLABLE")
    default_value = fm.get("default_value")
    errs: list[dict] = []

    if source not in raw:
        errs.append(
            {
                "entity_type": entity_type,
                "row": row_idx,
                "field": target,
                "level": "field",
                "code": "source_field_missing",
                "message": f"source field {source} not found in row {row_idx}",
            }
        )
        return {
            "target_attr": target,
            "source_field": source,
            "value": None,
            "status": "error",
            "message": "source missing",
        }, errs

    raw_value = raw.get(source)
    is_empty = raw_value is None or raw_value == ""

    if is_empty:
        if null_policy == "REQUIRED":
            errs.append(
                {
                    "entity_type": entity_type,
                    "row": row_idx,
                    "field": target,
                    "level": "field",
                    "code": "required_violation",
                    "message": f"required field {target} empty at row {row_idx}",
                }
            )
            return {
                "target_attr": target,
                "source_field": source,
                "value": None,
                "status": "error",
                "message": "required empty",
            }, errs
        elif null_policy == "DEFAULT":
            return {
                "target_attr": target,
                "source_field": source,
                "value": default_value,
                "status": "ok",
                "message": "default applied",
            }, errs
        elif null_policy == "SKIP":
            return {
                "target_attr": target,
                "source_field": source,
                "value": None,
                "status": "empty",
                "message": "skipped",
            }, errs
        else:
            return {
                "target_attr": target,
                "source_field": source,
                "value": None,
                "status": "empty",
                "message": "nullable empty",
            }, errs

    converted, conv_err = _apply_transform(
        transform, transform_params, raw_value, target, row_idx, entity_type
    )
    if conv_err:
        errs.append(conv_err)
        return {
            "target_attr": target,
            "source_field": source,
            "value": None,
            "status": "error",
            "message": conv_err.get("message"),
        }, errs
    return {
        "target_attr": target,
        "source_field": source,
        "value": converted,
        "status": "ok",
        "message": None,
    }, errs


def _apply_transform(
    transform: str, params: dict, value, target, row_idx, entity_type
) -> tuple[object | None, dict | None]:
    """A12：日期/枚举/小数/模板转换。"""
    if transform == "IDENTITY":
        return value, None
    if transform == "TEMPLATE":
        template = params.get("template", "{value}")
        try:
            return template.replace("{value}", str(value)), None
        except Exception as e:
            return None, {
                "entity_type": entity_type,
                "row": row_idx,
                "field": target,
                "level": "field",
                "code": "transform_failed",
                "message": f"template error: {e}",
            }
    if transform == "DATE":
        s = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date().isoformat(), None
            except ValueError:
                continue
        return None, {
            "entity_type": entity_type,
            "row": row_idx,
            "field": target,
            "level": "field",
            "code": "date_parse_failed",
            "message": f"cannot parse date: {value}",
        }
    if transform == "ENUM":
        mapping = params.get("mapping", {})
        mapped = mapping.get(str(value))
        if mapped is None:
            return None, {
                "entity_type": entity_type,
                "row": row_idx,
                "field": target,
                "level": "field",
                "code": "enum_unmapped",
                "message": f"enum value {value} not in mapping",
            }
        return mapped, None
    if transform == "DECIMAL":
        precision = int(params.get("precision", 2))
        try:
            d = Decimal(str(value))
            quant = Decimal(10) ** (-precision)
            return str(d.quantize(quant)), None
        except (InvalidOperation, ValueError) as e:
            return None, {
                "entity_type": entity_type,
                "row": row_idx,
                "field": target,
                "level": "field",
                "code": "decimal_parse_failed",
                "message": f"decimal error: {e}",
            }
    return value, None


def _compile_relation(
    rm: dict,
    engine,
    kind: str,
    table_set: set[str],
    limit: int,
) -> tuple[dict, list[dict]]:
    table = rm.get("table", "")
    schema = rm.get("schema", "main")
    rel_type = rm.get("relation_type", "")
    mode = rm.get("mode", "")
    errs: list[dict] = []

    if not _table_in_catalog(table, schema, table_set):
        errs.append(
            {
                "relation_type": rel_type,
                "table": table,
                "level": "table",
                "code": "table_not_found",
                "message": f"table {table} not in catalog",
            }
        )
        return {
            "relation_type": rel_type,
            "mode": mode,
            "table": table,
            "rows": [],
            "errors": errs,
        }, errs

    qualified = f'"{schema}"."{table}"' if schema and schema != "main" else f'"{table}"'
    sql = text(f"SELECT * FROM {qualified} LIMIT :lim")
    try:
        with engine.connect() as conn:
            result = conn.execute(sql, {"lim": limit})
            raw_rows = [dict(r._mapping) for r in result.fetchmany(limit)]
    except Exception as e:
        errs.append(
            {
                "relation_type": rel_type,
                "table": table,
                "level": "table",
                "code": "query_failed",
                "message": str(e)[:200],
            }
        )
        return {
            "relation_type": rel_type,
            "mode": mode,
            "table": table,
            "rows": [],
            "errors": errs,
        }, errs

    compiled_rows: list[dict] = []
    for idx, raw in enumerate(raw_rows):
        if mode == "FK":
            fk_field = rm.get("fk_field")
            if not fk_field:
                errs.append(
                    {
                        "relation_type": rel_type,
                        "level": "config",
                        "code": "missing_fk_field",
                        "message": "FK mode requires fk_field",
                    }
                )
                continue
            src_val = raw.get(fk_field)
            if src_val is None or src_val == "":
                errs.append(
                    {
                        "relation_type": rel_type,
                        "table": table,
                        "row": idx,
                        "field": fk_field,
                        "level": "field",
                        "code": "empty_endpoint",
                        "message": f"fk field {fk_field} empty at row {idx}",
                    }
                )
            compiled_rows.append(
                {"row_index": idx, "source_value": src_val, "fk_field": fk_field}
            )
        else:
            src = rm.get("source") or {}
            tgt = rm.get("target") or {}
            src_field = src.get("field")
            tgt_field = tgt.get("field")
            if not src_field or not tgt_field:
                errs.append(
                    {
                        "relation_type": rel_type,
                        "level": "config",
                        "code": "missing_endpoint_field",
                        "message": "source/target field missing",
                    }
                )
                continue
            src_val = raw.get(src_field)
            tgt_val = raw.get(tgt_field)
            if src_val is None or src_val == "":
                errs.append(
                    {
                        "relation_type": rel_type,
                        "table": table,
                        "row": idx,
                        "field": src_field,
                        "level": "field",
                        "code": "empty_endpoint",
                        "message": f"source endpoint {src_field} empty at row {idx}",
                    }
                )
            if tgt_val is None or tgt_val == "":
                errs.append(
                    {
                        "relation_type": rel_type,
                        "table": table,
                        "row": idx,
                        "field": tgt_field,
                        "level": "field",
                        "code": "empty_endpoint",
                        "message": f"target endpoint {tgt_field} empty at row {idx}",
                    }
                )
            attrs = {}
            if mode == "ASSOCIATIVE":
                for a in rm.get("attributes", []):
                    af = a.get("field")
                    if af and af in raw:
                        attrs[a.get("attr", af)] = raw.get(af)
            compiled_rows.append(
                {
                    "row_index": idx,
                    "source": src_val,
                    "target": tgt_val,
                    "attributes": attrs,
                }
            )
    return {
        "relation_type": rel_type,
        "mode": mode,
        "table": table,
        "rows": compiled_rows,
        "errors": errs,
    }, errs
