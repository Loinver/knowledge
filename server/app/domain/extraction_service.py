"""抽取引擎（H-32）。

四阶段：实体映射 → 关系映射 → 规则检查 → 隔离。
幂等：基于稳定 IRI（namespace + entity_type + row_key），重跑 IRI 集合一致。
失败保护：零产出判 FAILED，is_current 不动；可从历史成功运行切回。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.mapping_compiler import _apply_transform
from app.domain.metadata_service import get_latest_snapshot
from app.domain.source_service import _build_engine, get_datasource
from app.models.data_access import Datasource, MappingRevision
from app.models.enums import RunResult
from app.models.extraction import (
    DerivedEdge,
    EntityIdentity,
    ExtractionRun,
    FactEvidence,
    GraphRevision,
    GraphTriple,
    Quarantine,
)


def start_run(
    session: Session,
    mapping_revision_id: int,
    datasource_id: int,
    namespace: str = "https://example.org/kg/",
) -> ExtractionRun:
    """启动抽取运行。同步执行四阶段，状态机落库。"""
    rev = session.get(MappingRevision, mapping_revision_id)
    if rev is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"mapping_revision_id": mapping_revision_id},
        )
    if rev.revision == 0:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"reason": "cannot_run_draft", "revision": mapping_revision_id},
        )
    ds = get_datasource(session, datasource_id)
    snap = get_latest_snapshot(session, datasource_id)
    if snap is None:
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"datasource_id": datasource_id, "reason": "no_metadata_snapshot"},
        )

    cfg = {
        "mapping_revision_id": mapping_revision_id,
        "datasource_id": datasource_id,
        "namespace": namespace,
        "onto_version": rev.onto_version,
    }
    run = ExtractionRun(
        mapping_revision_id=mapping_revision_id,
        status=RunResult.PARTIAL,
        cfg_snapshot=cfg,
        fingerprint=None,
        counts={},
    )
    session.add(run)
    session.flush()

    try:
        counts = _execute_four_phases(session, run, rev, ds, snap.catalog, namespace)
    except Exception as e:
        run.status = RunResult.FAILED
        run.finished_at = datetime.now(UTC)
        run.counts = {"error": str(e)[:500]}
        session.flush()
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE,
            {"run_id": run.id, "reason": str(e)[:200]},
        ) from e

    run.counts = counts
    run.fingerprint = _compute_fingerprint(cfg, counts)
    # 失败保护：零产出判 FAILED
    zero_output = (
        counts.get("entity_count", 0) == 0 and counts.get("triple_count", 0) == 0
    )
    only_quarantine = (
        counts.get("quarantine_count", 0) > 0 and counts.get("entity_count", 0) == 0
    )
    if zero_output or only_quarantine:
        run.status = RunResult.FAILED
    else:
        run.status = (
            RunResult.SUCCESS
            if counts.get("quarantine_count", 0) == 0
            else RunResult.PARTIAL
        )
    run.finished_at = datetime.now(UTC)
    session.flush()

    # 成功才创建 graph_revision 并设 is_current（失败不覆盖）
    if run.status in (RunResult.SUCCESS, RunResult.PARTIAL):
        _publish_graph_revision(session, run)
    return run


def _execute_four_phases(
    session: Session,
    run: ExtractionRun,
    rev: MappingRevision,
    ds: Datasource,
    catalog: dict,
    namespace: str,
) -> dict:
    """四阶段执行。返回计数。"""
    engine = _build_engine(ds)
    table_set = _index_catalog_tables(catalog)
    # 先建一个临时 graph_revision 给 entity/triple 挂（run 结束时统一发布）
    gr = GraphRevision(run_id=run.id, is_current=False, publishable=False)
    session.add(gr)
    session.flush()

    entity_iri_index: dict[str, dict] = {}  # IRI -> {type, row_key}
    quarantine_count = 0
    evidence_count = 0

    # 阶段1：实体映射
    for em in rev.entity_maps or []:
        n, q = _phase1_entity(
            session, run, gr, em, engine, table_set, namespace, entity_iri_index
        )
        quarantine_count += q
        evidence_count += n

    # 阶段2：关系映射
    triple_count = 0
    rel_evidence = 0
    for rm in rev.rel_maps or []:
        t, q, e = _phase2_relation(
            session, run, gr, rm, engine, table_set, namespace, entity_iri_index
        )
        triple_count += t
        quarantine_count += q
        rel_evidence += e

    entity_count = len(entity_iri_index)

    counts = {
        "entity_count": entity_count,
        "triple_count": triple_count,
        "quarantine_count": quarantine_count,
        "evidence_count": evidence_count + rel_evidence,
        "derived_edge_count": 0,
    }
    # 阶段3 + 4 已在 phase1/phase2 内联（违规进 quarantine）
    return counts


def _index_catalog_tables(catalog: dict) -> set[str]:
    tables: set[str] = set()
    for s in catalog.get("schemas", []):
        sname = s.get("schema", "main")
        for t in s.get("tables", []):
            tables.add(f"{sname}:{t['name']}")
            tables.add(t["name"])
    return tables


def _table_in_catalog(table: str, schema: str, table_set: set[str]) -> bool:
    return table in table_set or f"{schema}:{table}" in table_set


def _stable_iri(namespace: str, entity_type: str, row_key: str) -> str:
    """稳定 IRI：namespace + entity_type + '-' + row_key。幂等基础。"""
    safe_key = str(row_key).replace(" ", "_").replace("|", "-")
    return f"{namespace}{entity_type}/{safe_key}"


def _phase1_entity(
    session: Session,
    run: ExtractionRun,
    gr: GraphRevision,
    em: dict,
    engine: Engine,
    table_set: set[str],
    namespace: str,
    entity_iri_index: dict,
) -> tuple[int, int]:
    """阶段1：实体映射。返回 (evidence_count, quarantine_count)。"""
    table = em.get("table", "")
    schema = em.get("schema", "main")
    entity_type = em.get("entity_type", "")
    field_maps = em.get("field_maps", [])
    key_fields = em.get("key_fields", [])
    evidence_n = 0
    quarantine_n = 0

    if not _table_in_catalog(table, schema, table_set):
        session.add(
            _make_quarantine(
                run,
                table,
                "N/A",
                "_table",
                None,
                ["table_check"],
                "table_not_in_catalog",
            )
        )
        return 0, 1

    qualified = f'"{schema}"."{table}"' if schema and schema != "main" else f'"{table}"'
    sql = text(f"SELECT * FROM {qualified}")
    try:
        with engine.connect() as conn:
            result = conn.execute(sql)
            raw_rows = [dict(r._mapping) for r in result.fetchall()]
    except Exception as e:
        session.add(
            _make_quarantine(
                run, table, "N/A", "_query", str(e)[:200], ["query"], "query_failed"
            )
        )
        return 0, 1

    for idx, raw in enumerate(raw_rows):
        # row_key
        if key_fields:
            key_parts = [str(raw.get(k)) for k in key_fields if raw.get(k) is not None]
            row_key = "|".join(key_parts) if key_parts else f"row-{idx}"
        else:
            row_key = f"row-{idx}"

        # 空键检查
        empty_keys = [k for k in key_fields if raw.get(k) is None or raw.get(k) == ""]
        for ek in empty_keys:
            session.add(
                _make_quarantine(
                    run,
                    table,
                    row_key,
                    ek,
                    str(raw.get(ek)),
                    ["key_check"],
                    "empty_key",
                )
            )
            quarantine_n += 1

        iri = _stable_iri(namespace, entity_type, row_key)
        # 转换字段
        attrs: dict = {}
        for fm in field_maps:
            target = fm.get("target_attr", "")
            source = fm.get("source_field", "")
            transform = fm.get("transform", "IDENTITY")
            params = fm.get("transform_params") or {}
            null_policy = fm.get("null_policy", "NULLABLE")
            default_value = fm.get("default_value")
            raw_value = raw.get(source)
            is_empty = raw_value is None or raw_value == ""
            if is_empty:
                if null_policy == "REQUIRED":
                    session.add(
                        _make_quarantine(
                            run,
                            table,
                            row_key,
                            source,
                            str(raw_value),
                            ["transform"],
                            "required_violation",
                        )
                    )
                    quarantine_n += 1
                    continue
                elif null_policy == "DEFAULT":
                    attrs[target] = default_value
                elif null_policy == "SKIP":
                    continue
                else:
                    attrs[target] = None
            else:
                converted, conv_err = _apply_transform(
                    transform, params, raw_value, target, idx, entity_type
                )
                if conv_err:
                    session.add(
                        _make_quarantine(
                            run,
                            table,
                            row_key,
                            source,
                            str(raw_value),
                            ["transform:" + transform],
                            conv_err.get("code", "transform_failed"),
                        )
                    )
                    quarantine_n += 1
                else:
                    attrs[target] = converted

        # 存 EntityIdentity（幂等：同 IRI 更新）
        if iri not in entity_iri_index:
            ei = EntityIdentity(
                graph_revision_id=gr.id,
                iri=iri,
                type_iri=f"{namespace}{entity_type}",
                row_key=row_key,
                attrs=attrs,
            )
            session.add(ei)
            entity_iri_index[iri] = {
                "type": entity_type,
                "row_key": row_key,
                "table": table,
            }
        # 证据
        ev = FactEvidence(
            graph_revision_id=gr.id,
            subject=iri,
            predicate="_entity_attrs",
            object_=iri,
            source_id=run.cfg_snapshot.get("datasource_id", 0)
            if isinstance(run.cfg_snapshot, dict)
            else 0,
            table_name=table,
            row_key=row_key,
            columns=[fm.get("source_field") for fm in field_maps],
            run_id=run.id,
            evidence_type="ENTITY",
        )
        session.add(ev)
        evidence_n += 1
    session.flush()
    return evidence_n, quarantine_n


def _phase2_relation(
    session: Session,
    run: ExtractionRun,
    gr: GraphRevision,
    rm: dict,
    engine: Engine,
    table_set: set[str],
    namespace: str,
    entity_iri_index: dict,
) -> tuple[int, int, int]:
    """阶段2：关系映射。返回 (triple_count, quarantine_count, evidence_count)。"""
    table = rm.get("table", "")
    schema = rm.get("schema", "main")
    rel_type = rm.get("relation_type", "")
    mode = rm.get("mode", "")
    triple_n = 0
    quarantine_n = 0
    evidence_n = 0
    ds_id = (
        run.cfg_snapshot.get("datasource_id", 0)
        if isinstance(run.cfg_snapshot, dict)
        else 0
    )

    if not _table_in_catalog(table, schema, table_set):
        session.add(
            _make_quarantine(
                run,
                table,
                "N/A",
                "_table",
                None,
                ["table_check"],
                "table_not_in_catalog",
            )
        )
        return 0, 1, 0

    qualified = f'"{schema}"."{table}"' if schema and schema != "main" else f'"{table}"'
    sql = text(f"SELECT * FROM {qualified}")
    try:
        with engine.connect() as conn:
            result = conn.execute(sql)
            raw_rows = [dict(r._mapping) for r in result.fetchall()]
    except Exception as e:
        session.add(
            _make_quarantine(
                run, table, "N/A", "_query", str(e)[:200], ["query"], "query_failed"
            )
        )
        return 0, 1, 0

    for idx, raw in enumerate(raw_rows):
        row_key = f"row-{idx}"
        if mode == "FK":
            fk_field = rm.get("fk_field", "")
            src_val = raw.get(fk_field)
            if src_val is None or src_val == "":
                session.add(
                    _make_quarantine(
                        run,
                        table,
                        row_key,
                        fk_field,
                        str(src_val),
                        ["fk"],
                        "empty_endpoint",
                    )
                )
                quarantine_n += 1
                continue
            # FK: subject 是当前表实体，object 是被引用表实体
            subject_key = str(raw.get("id", f"fk-{idx}"))
            subject_iri = _lookup_or_stub(
                entity_iri_index, namespace, table, subject_key, session, gr
            )
            object_iri = _resolve_ref_iri(
                entity_iri_index, namespace, src_val, session, gr
            )
            triple = GraphTriple(
                graph_revision_id=gr.id,
                subject=subject_iri,
                predicate=rel_type,
                object_=object_iri,
            )
            session.add(triple)
            session.add(
                _make_evidence(
                    gr,
                    run,
                    subject_iri,
                    rel_type,
                    object_iri,
                    ds_id,
                    table,
                    row_key,
                    [fk_field],
                    "RELATION",
                )
            )
            triple_n += 1
            evidence_n += 1
        else:  # JUNCTION / ASSOCIATIVE
            src = rm.get("source") or {}
            tgt = rm.get("target") or {}
            src_field = src.get("field", "")
            tgt_field = tgt.get("field", "")
            src_val = raw.get(src_field)
            tgt_val = raw.get(tgt_field)
            if src_val is None or src_val == "":
                session.add(
                    _make_quarantine(
                        run,
                        table,
                        row_key,
                        src_field,
                        str(src_val),
                        ["endpoint"],
                        "empty_endpoint",
                    )
                )
                quarantine_n += 1
            if tgt_val is None or tgt_val == "":
                session.add(
                    _make_quarantine(
                        run,
                        table,
                        row_key,
                        tgt_field,
                        str(tgt_val),
                        ["endpoint"],
                        "empty_endpoint",
                    )
                )
                quarantine_n += 1
            if src_val is None or tgt_val is None:
                continue
            src_iri = _lookup_or_stub(
                entity_iri_index,
                namespace,
                src.get("ref_table", ""),
                str(src_val),
                session,
                gr,
            )
            tgt_iri = _lookup_or_stub(
                entity_iri_index,
                namespace,
                tgt.get("ref_table", ""),
                str(tgt_val),
                session,
                gr,
            )
            triple = GraphTriple(
                graph_revision_id=gr.id,
                subject=src_iri,
                predicate=rel_type,
                object_=tgt_iri,
            )
            session.add(triple)
            cols = [src_field, tgt_field]
            if mode == "ASSOCIATIVE":
                for a in rm.get("attributes", []):
                    af = a.get("field", "")
                    if af:
                        cols.append(af)
            session.add(
                _make_evidence(
                    gr,
                    run,
                    src_iri,
                    rel_type,
                    tgt_iri,
                    ds_id,
                    table,
                    row_key,
                    cols,
                    "RELATION",
                )
            )
            triple_n += 1
            evidence_n += 1
    session.flush()
    return triple_n, quarantine_n, evidence_n


def _lookup_or_stub(
    entity_index: dict,
    namespace: str,
    table: str,
    key: str,
    session: Session,
    gr: GraphRevision,
) -> str:
    """查已建实体 IRI（同表 + 同 row_key），找不到建 stub。"""
    key_str = str(key)
    # 先在已建实体里找同表同 row_key
    for iri_ex, info in entity_index.items():
        if info.get("table") == table and info.get("row_key") == key_str:
            return iri_ex
    safe_key = key_str.replace(" ", "_")
    iri = f"{namespace}{table}/{safe_key}"
    if iri not in entity_index:
        ei = EntityIdentity(
            graph_revision_id=gr.id,
            iri=iri,
            type_iri=f"{namespace}{table}",
            row_key=key_str,
            attrs={},
        )
        # session 由调用方传入
        session.add(ei)
        entity_index[iri] = {
            "type": table,
            "row_key": key_str,
            "table": table,
            "stub": True,
        }
    return iri


def _resolve_ref_iri(
    entity_index: dict,
    namespace: str,
    val: object,
    session: Session,
    gr: GraphRevision,
) -> str:
    """FK 模式：在已建实体里按 row_key 匹配引用值，找不到建 stub。"""
    val_str = str(val)
    for iri_ex, info in entity_index.items():
        if info.get("row_key") == val_str:
            return iri_ex
    safe_val = val_str.replace(" ", "_")
    iri = f"{namespace}ref/{safe_val}"
    if iri not in entity_index:
        ei = EntityIdentity(
            graph_revision_id=gr.id,
            iri=iri,
            type_iri=f"{namespace}ref",
            row_key=val_str,
            attrs={},
        )
        session.add(ei)
        entity_index[iri] = {
            "type": "ref",
            "row_key": val_str,
            "table": "ref",
            "stub": True,
        }
    return iri


def _make_quarantine(
    run: ExtractionRun,
    table: str,
    row_key: str,
    field: str,
    raw_value: object,
    chain: list[str],
    rule_id: str,
) -> Quarantine:
    return Quarantine(
        run_id=run.id,
        table_name=table,
        row_key=str(row_key),
        field=str(field),
        raw_value=str(raw_value) if raw_value is not None else None,
        transform_chain=list(chain),
        rule_id=str(rule_id),
    )


def _make_evidence(
    gr: GraphRevision,
    run: ExtractionRun,
    subject: str,
    predicate: str,
    object_: str,
    source_id: int,
    table: str,
    row_key: str,
    columns: list[str],
    ev_type: str,
) -> FactEvidence:
    return FactEvidence(
        graph_revision_id=gr.id,
        subject=subject,
        predicate=predicate,
        object_=object_,
        source_id=source_id,
        table_name=table,
        row_key=str(row_key),
        columns=list(columns),
        run_id=run.id,
        evidence_type=ev_type,
    )


def _compute_fingerprint(cfg: dict, counts: dict) -> str:
    """幂等指纹：基于配置 + 实体 IRI 数 + 三元组数。"""
    raw = f"{cfg}|{counts.get('entity_count', 0)}|{counts.get('triple_count', 0)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _publish_graph_revision(
    session: Session, run: ExtractionRun
) -> GraphRevision | None:
    """成功运行创建 graph_revision 并设 is_current。失败不动 is_current。"""
    gr = (
        session.execute(select(GraphRevision).where(GraphRevision.run_id == run.id))
        .scalars()
        .first()
    )
    if gr is None:
        return None
    gr.publishable = True
    # 清除旧的 is_current
    old_current = (
        session.execute(select(GraphRevision).where(GraphRevision.is_current.is_(True)))
        .scalars()
        .all()
    )
    for o in old_current:
        o.is_current = False
    gr.is_current = True
    session.flush()
    return gr


def get_run(session: Session, run_id: int) -> ExtractionRun:
    run = session.get(ExtractionRun, run_id)
    if run is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"run_id": run_id})
    return run


def list_runs(
    session: Session, page: int = 1, page_size: int = 50
) -> tuple[list[ExtractionRun], int]:
    stmt = select(ExtractionRun).order_by(ExtractionRun.id.desc())
    total = len(list(session.execute(select(ExtractionRun)).scalars()))
    items = list(
        session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return items, total


def get_current_graph(session: Session) -> GraphRevision | None:
    return (
        session.execute(select(GraphRevision).where(GraphRevision.is_current.is_(True)))
        .scalars()
        .first()
    )


def switch_current(session: Session, graph_revision_id: int) -> GraphRevision:
    """结果集切换：任一历史成功运行可设为当前。"""
    gr = session.get(GraphRevision, graph_revision_id)
    if gr is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"graph_revision_id": graph_revision_id}
        )
    run = session.get(ExtractionRun, gr.run_id)
    if run is None or run.status not in (RunResult.SUCCESS, RunResult.PARTIAL):
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {
                "reason": "cannot_switch_failed_run",
                "graph_revision_id": graph_revision_id,
            },
        )
    old_current = (
        session.execute(select(GraphRevision).where(GraphRevision.is_current.is_(True)))
        .scalars()
        .all()
    )
    for o in old_current:
        o.is_current = False
    gr.is_current = True
    session.flush()
    return gr


def list_entity_identities(
    session: Session, gr_id: int, q: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[EntityIdentity], int]:
    stmt = select(EntityIdentity).where(EntityIdentity.graph_revision_id == gr_id)
    if q:
        stmt = stmt.where(EntityIdentity.iri.ilike(f"%{q}%"))
    total = len(list(session.execute(stmt).scalars()))
    items = list(
        session.execute(
            stmt.order_by(EntityIdentity.iri)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars()
    )
    return items, total


def list_triples(
    session: Session, gr_id: int, subject: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[GraphTriple], int]:
    stmt = select(GraphTriple).where(GraphTriple.graph_revision_id == gr_id)
    if subject:
        stmt = stmt.where(GraphTriple.subject == subject)
    total = len(list(session.execute(stmt).scalars()))
    items = list(
        session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return items, total


def get_evidence(
    session: Session, subject: str, predicate: str, object_: str
) -> list[FactEvidence]:
    return list(
        session.execute(
            select(FactEvidence).where(
                FactEvidence.subject == subject,
                FactEvidence.predicate == predicate,
                FactEvidence.object_ == object_,
            )
        )
        .scalars()
        .all()
    )


def get_entity_detail(session: Session, iri: str) -> dict:
    """实体详情：属性 + 出边 + 入边 + 派生边 + 证据。"""
    gr = get_current_graph(session)
    if gr is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"reason": "no_current_graph"})
    entity = (
        session.execute(
            select(EntityIdentity).where(
                EntityIdentity.iri == iri, EntityIdentity.graph_revision_id == gr.id
            )
        )
        .scalars()
        .first()
    )
    if entity is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"iri": iri})
    out_edges = list(
        session.execute(
            select(GraphTriple).where(
                GraphTriple.subject == iri, GraphTriple.graph_revision_id == gr.id
            )
        )
        .scalars()
        .all()
    )
    in_edges = list(
        session.execute(
            select(GraphTriple).where(
                GraphTriple.object_ == iri, GraphTriple.graph_revision_id == gr.id
            )
        )
        .scalars()
        .all()
    )
    derived = list(
        session.execute(
            select(DerivedEdge).where(
                (DerivedEdge.subject == iri) | (DerivedEdge.object_ == iri),
                DerivedEdge.graph_revision_id == gr.id,
            )
        )
        .scalars()
        .all()
    )
    evidence = list(
        session.execute(
            select(FactEvidence).where(
                (FactEvidence.subject == iri) | (FactEvidence.object_ == iri),
                FactEvidence.graph_revision_id == gr.id,
            )
        )
        .scalars()
        .all()
    )
    return {
        "entity": entity,
        "out_edges": out_edges,
        "in_edges": in_edges,
        "derived_edges": derived,
        "evidence": evidence,
    }


def list_quarantine(session: Session, run_id: int) -> list[Quarantine]:
    return list(
        session.execute(
            select(Quarantine)
            .where(Quarantine.run_id == run_id)
            .order_by(Quarantine.id)
        )
        .scalars()
        .all()
    )
