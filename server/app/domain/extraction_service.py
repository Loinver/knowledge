"""抽取引擎（H-32）。

四阶段：实体映射 → 关系映射 → 规则校验 → 派生推导。
幂等：基于稳定 IRI（namespace + entity_type + row_key/业务键），重跑 IRI 集合一致。
失败保护：零产出判 FAILED，is_current 不动；可从历史成功运行切回。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import bindparam, func, inspect, literal_column, quoted_name, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.connectors.sql import select_source_rows
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.derivation_service import run_derivation_stage
from app.domain.extraction_rule_stage import run_rule_stage
from app.domain.mapping_compiler import _apply_transform
from app.domain.metadata_service import get_latest_snapshot
from app.domain.source_service import datasource_engine, get_datasource
from app.models.data_access import Datasource, Mapping, MappingRevision
from app.models.domain import OntologyRevision, OntologyRuleRef
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
from app.models.governance import Rule


def _load_frozen_pins(session: Session, rev: MappingRevision) -> dict:
    """抽取运行级冻结引用：映射/本体/资源/规则版本，写入每条证据。

    规则钉扎取本体发布时的 pinned_revision；资源版本取本体版本的
    resource_versions 快照。上游改版不会静默改变证据解释口径。
    """
    mapping = session.get(Mapping, rev.mapping_id)
    if mapping is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"mapping_id": rev.mapping_id})
    onto_rev = (
        session.execute(
            select(OntologyRevision).where(
                OntologyRevision.ontology_id == mapping.ontology_id,
                OntologyRevision.revision == rev.onto_version,
            )
        )
        .scalars()
        .first()
    )
    resource_versions: dict = dict(onto_rev.resource_versions or {}) if onto_rev else {}
    rule_refs = session.execute(
        select(OntologyRuleRef, Rule.identifier)
        .join(Rule, Rule.id == OntologyRuleRef.rule_id)
        .where(OntologyRuleRef.ontology_id == mapping.ontology_id)
    ).all()
    return {
        "mapping_revision_id": rev.id,
        "ontology_revision": rev.onto_version,
        "ontology_id": mapping.ontology_id,
        "resource_versions": resource_versions,
        "rule_revisions": {
            identifier: ref.pinned_revision for ref, identifier in rule_refs
        },
    }


class ExtractionCancelledError(Exception):
    """协作式取消：任务在阶段边界安全中断，不发布结果集。"""


def start_run(
    session: Session,
    mapping_revision_id: int,
    datasource_id: int,
    namespace: str = "https://example.org/kg/",
    *,
    progress: Callable[[str, dict], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    watermarks: dict | None = None,
    watermark_out: dict | None = None,
) -> ExtractionRun:
    """启动抽取运行。同步执行四阶段，状态机落库。

    progress / cancel_check / watermarks 供异步任务使用：进度按阶段
    回调，取消在阶段边界协作生效，水位用于增量过滤与新水位写出。
    """
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

    pins = _load_frozen_pins(session, rev)
    cfg = {
        "mapping_revision_id": mapping_revision_id,
        "datasource_id": datasource_id,
        "namespace": namespace,
        "onto_version": rev.onto_version,
        "pins": pins,
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
        counts = _execute_four_phases(
            session,
            run,
            rev,
            ds,
            snap.catalog,
            namespace,
            progress=progress,
            cancel_check=cancel_check,
            watermarks=watermarks,
            watermark_out=watermark_out,
        )
    except Exception:
        run.status = RunResult.FAILED
        run.finished_at = datetime.now(UTC)
        run.counts = {"error": "source_execution_failed"}
        session.flush()
        raise KGError(
            ErrorCode.SOURCE_UNREACHABLE,
            {"run_id": run.id, "reason": "source_execution_failed"},
        ) from None

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
    *,
    progress: Callable[[str, dict], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    watermarks: dict | None = None,
    watermark_out: dict | None = None,
) -> dict:
    """四阶段执行。返回计数。

    阶段1/2 在源库上抽取；阶段3 规则校验与阶段4 派生推导在本库
    刚建好的候选图（gr）上执行，不回读源库。
    """
    table_set = _index_catalog_tables(catalog)
    # 先建一个临时 graph_revision 给 entity/triple 挂（run 结束时统一发布）
    gr = GraphRevision(run_id=run.id, is_current=False, publishable=False)
    session.add(gr)
    session.flush()

    entity_iri_index: dict[str, dict] = {}  # IRI -> {type, row_key}
    # (table, row_key) / ("type:<entity_type>", 业务键) -> IRI，端点解析索引
    key_index: dict[tuple[str, str], str] = {}

    def _check_cancel() -> None:
        if cancel_check is not None and cancel_check():
            raise ExtractionCancelledError()

    def _report(phase: str, extra: dict) -> None:
        if progress is not None:
            progress(
                phase,
                {
                    "entity_count": len(entity_iri_index),
                    "triple_count": triple_count,
                    "quarantine_count": quarantine_count,
                    **extra,
                },
            )

    quarantine_count = 0
    evidence_count = 0

    triple_count = 0
    rel_evidence = 0
    with datasource_engine(ds) as engine:
        _check_cancel()
        # 阶段1：实体映射
        for em in rev.entity_maps or []:
            n, q = _phase1_entity(
                session,
                run,
                gr,
                em,
                engine,
                table_set,
                namespace,
                entity_iri_index,
                key_index,
                watermarks=watermarks,
                watermark_out=watermark_out,
            )
            quarantine_count += q
            evidence_count += n
        _report("entities", {"evidence_count": evidence_count})

        _check_cancel()
        # 阶段2：关系映射
        for rm in rev.rel_maps or []:
            t, q, e = _phase2_relation(
                session,
                run,
                gr,
                rm,
                engine,
                table_set,
                namespace,
                entity_iri_index,
                key_index,
            )
            triple_count += t
            quarantine_count += q
            rel_evidence += e
        _report("relations", {"evidence_count": evidence_count + rel_evidence})

    entity_count = len(entity_iri_index)

    _check_cancel()
    # 阶段3：规则校验（实例校验报告 + DATA 规则执行，命中写隔离）
    rule_stage = run_rule_stage(session, run, gr, rev)
    quarantine_count += rule_stage["quarantined_by_rule"]
    _report("rules", {"evidence_count": evidence_count + rel_evidence})

    _check_cancel()
    # 阶段4：派生推导（DERIVATION 规则执行，写 DerivedEdge）
    derived_count = run_derivation_stage(session, run, gr, rev)
    _report("derivation", {"evidence_count": evidence_count + rel_evidence})

    counts = {
        "entity_count": entity_count,
        "triple_count": triple_count,
        "quarantine_count": quarantine_count,
        "evidence_count": evidence_count + rel_evidence,
        "derived_edge_count": derived_count,
        "rule_violation_count": rule_stage["rule_violation_count"],
        "validation_summary": rule_stage["validation_summary"],
        "rule_results": rule_stage["rule_results"],
    }
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


def _greater_value(candidate: object, incumbent: object | None) -> bool:
    """水位取 max：数值按数值比较，其余按字符串；类型混排时保守取候选。"""
    if incumbent is None:
        return True
    if isinstance(candidate, int | float) and isinstance(incumbent, int | float):
        return float(candidate) > float(incumbent)
    return str(candidate) > str(incumbent)


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
    key_index: dict[tuple[str, str], str],
    *,
    watermarks: dict | None = None,
    watermark_out: dict | None = None,
) -> tuple[int, int]:
    """阶段1：实体映射。返回 (evidence_count, quarantine_count)。

    match_keys 存在时按业务键生成 IRI：多张来源表映射到同一 entity_type
    且业务键值相同 → 融合为同一实体，但每张来源表各自保留证据。
    """
    table = em.get("table", "")
    schema = em.get("schema", "main")
    entity_type = em.get("entity_type", "")
    field_maps = em.get("field_maps", [])
    key_fields = em.get("key_fields", [])
    match_keys = em.get("match_keys") or []
    incremental_field = em.get("incremental_field")
    watermark: object | None = None
    if watermarks and incremental_field:
        entry = watermarks.get(table) or {}
        if entry.get("field") == incremental_field:
            watermark = entry.get("value")
    watermark_max: object | None = None
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

    sql = select_source_rows(table, schema)
    query_params: dict = {}
    if watermark is not None and incremental_field:
        sql = sql.where(
            literal_column(quoted_name(incremental_field, True))
            > bindparam("kg_watermark")
        )
        query_params["kg_watermark"] = watermark
    try:
        with engine.connect() as conn:
            result = conn.execute(sql, query_params)
            raw_rows = [dict(r._mapping) for r in result.fetchall()]
    except Exception:
        session.add(
            _make_quarantine(
                run, table, "N/A", "_query", None, ["query"], "query_failed"
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

        if incremental_field:
            current = raw.get(incremental_field)
            if current is not None and _greater_value(current, watermark_max):
                watermark_max = current

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

        # 业务键（跨表融合）检查与 IRI 选择
        match_value = ""
        for mk in match_keys:
            value = raw.get(mk)
            if value is None or value == "":
                session.add(
                    _make_quarantine(
                        run,
                        table,
                        row_key,
                        mk,
                        str(value),
                        ["match_key"],
                        "empty_business_key",
                    )
                )
                quarantine_n += 1
            else:
                match_value = f"{match_value}|{value}" if match_value else str(value)
        identity_key = match_value if match_value else row_key
        iri = _stable_iri(namespace, entity_type, identity_key)
        key_index[(table, row_key)] = iri
        if match_value:
            key_index[(f"type:{entity_type}", match_value)] = iri
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
        session.add(
            _make_evidence(
                gr,
                run,
                iri,
                "_entity_attrs",
                iri,
                table,
                row_key,
                [fm.get("source_field") for fm in field_maps],
                "ENTITY",
            )
        )
        evidence_n += 1
    session.flush()
    if watermark_out is not None and incremental_field and watermark_max is not None:
        watermark_out[table] = {"field": incremental_field, "value": watermark_max}
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
    key_index: dict[tuple[str, str], str],
) -> tuple[int, int, int]:
    """阶段2：关系映射。返回 (triple_count, quarantine_count, evidence_count)。

    端点支持多候选（多态）：candidates 按列非空或 type_field 判别值选表，
    如股东表按 shareholder_type 决定引用自然人表或企业表。
    ASSOCIATIVE 关联属性写入边 props，使持股比例/金额/角色在图上可读。
    """
    table = rm.get("table", "")
    schema = rm.get("schema", "main")
    rel_type = rm.get("relation_type", "")
    mode = rm.get("mode", "")
    triple_n = 0
    quarantine_n = 0
    evidence_n = 0

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

    sql = select_source_rows(table, schema)
    try:
        with engine.connect() as conn:
            key_fields = (
                inspect(conn)
                .get_pk_constraint(table, schema=None if schema == "main" else schema)
                .get("constrained_columns", [])
            )
            result = conn.execute(sql)
            raw_rows = [dict(r._mapping) for r in result.fetchall()]
    except Exception:
        session.add(
            _make_quarantine(
                run, table, "N/A", "_query", None, ["query"], "query_failed"
            )
        )
        return 0, 1, 0

    attr_fields = [
        a.get("field", "") for a in rm.get("attributes", []) if a.get("field")
    ]
    # 二跳端点：预先把经由表整表载入（多态股东等结构），键为连接值
    src_via_rows = _load_via_rows(engine, rm.get("source"), table_set)
    tgt_via_rows = _load_via_rows(engine, rm.get("target"), table_set)

    def _quarantine_via_table(table_name: str) -> tuple[int, int, int]:
        # 经由表不在目录：整表隔离，不逐行报
        session.add(
            _make_quarantine(
                run,
                table_name,
                "N/A",
                "_table",
                None,
                ["table_check"],
                "table_not_in_catalog",
            )
        )
        return triple_n, quarantine_n + 1, evidence_n

    if isinstance(src_via_rows, str):
        return _quarantine_via_table(src_via_rows)
    if isinstance(tgt_via_rows, str):
        return _quarantine_via_table(tgt_via_rows)

    for idx, raw in enumerate(raw_rows):
        row_key = (
            "|".join(str(raw[key]) for key in key_fields)
            if key_fields
            else f"row-{idx}"
        )
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
                entity_iri_index, namespace, table, subject_key, session, gr, key_index
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
            src_eval = _endpoint_eval_row(src, raw, src_via_rows)
            tgt_eval = _endpoint_eval_row(tgt, raw, tgt_via_rows)
            src_cand = _pick_endpoint(src, src_eval) if src_eval else None
            tgt_cand = _pick_endpoint(tgt, tgt_eval) if tgt_eval else None
            if src_cand is None or tgt_cand is None:
                missing_spec = src if src_cand is None else tgt
                missing_eval = src_eval if src_cand is None else tgt_eval
                field = (
                    missing_spec.get("type_field")
                    or _endpoint_candidates(missing_spec)[0]["field"]
                )
                session.add(
                    _make_quarantine(
                        run,
                        table,
                        row_key,
                        field,
                        str(missing_eval.get(field)) if missing_eval else None,
                        ["endpoint"],
                        "empty_endpoint",
                    )
                )
                quarantine_n += 1
                continue
            src_val = src_eval.get(src_cand["field"]) if src_eval else None
            tgt_val = tgt_eval.get(tgt_cand["field"]) if tgt_eval else None
            src_iri = _lookup_or_stub(
                entity_iri_index,
                namespace,
                src_cand["ref_table"],
                str(src_val),
                session,
                gr,
                key_index,
                src_cand.get("ref_entity_type"),
            )
            tgt_iri = _lookup_or_stub(
                entity_iri_index,
                namespace,
                tgt_cand["ref_table"],
                str(tgt_val),
                session,
                gr,
                key_index,
                tgt_cand.get("ref_entity_type"),
            )
            props: dict = {}
            if mode == "ASSOCIATIVE":
                for a in rm.get("attributes", []):
                    af = a.get("field", "")
                    if af and raw.get(af) is not None:
                        props[a.get("attr", af)] = raw.get(af)
            triple = GraphTriple(
                graph_revision_id=gr.id,
                subject=src_iri,
                predicate=rel_type,
                object_=tgt_iri,
                props=props or None,
            )
            session.add(triple)
            cols = [src_cand["field"], tgt_cand["field"]]
            if src.get("type_field"):
                cols.append(src["type_field"])
            if tgt.get("type_field"):
                cols.append(tgt["type_field"])
            cols.extend(f for f in attr_fields if f not in cols)
            session.add(
                _make_evidence(
                    gr,
                    run,
                    src_iri,
                    rel_type,
                    tgt_iri,
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


def _endpoint_candidates(spec: dict) -> list[dict]:
    """端点候选归一：显式 candidates 优先，缺省回退单候选 field/ref_table。"""
    cands = spec.get("candidates") or []
    if cands:
        return list(cands)
    return [
        {
            "field": spec.get("field", ""),
            "ref_table": spec.get("ref_table", ""),
            "ref_field": spec.get("ref_field") or None,
            "when": None,
            "ref_entity_type": None,
        }
    ]


def _pick_endpoint(spec: dict, raw: dict) -> dict | None:
    """按判别字段或列非空顺序选出本行端点候选；无可用候选返回 None。"""
    cands = _endpoint_candidates(spec)
    type_field = spec.get("type_field")
    if type_field:
        type_value = raw.get(type_field)
        for cand in cands:
            if cand.get("when") == str(type_value) and raw.get(
                cand.get("field", "")
            ) not in (
                None,
                "",
            ):
                return cand
        return None
    for cand in cands:
        if raw.get(cand.get("field", "")) not in (None, ""):
            return cand
    return None


def _load_via_rows(
    engine: Engine, spec: dict | None, table_set: set[str]
) -> dict[str, dict] | str | None:
    """预载二跳端点的经由表：{连接值: 经由行}。

    返回 None 表示无 via；返回字符串表示经由表不在目录（调用方整表隔离）。
    """
    via = (spec or {}).get("via") if spec else None
    if not via:
        return None
    via_table = via.get("table", "")
    via_schema = "main"
    if not _table_in_catalog(via_table, via_schema, table_set):
        return via_table
    sql = select_source_rows(via_table, via_schema)
    try:
        with engine.connect() as conn:
            result = conn.execute(sql)
            rows = [dict(r._mapping) for r in result.fetchall()]
    except Exception:
        return via_table
    ref_field = via.get("ref_field", "id") or "id"
    return {str(row.get(ref_field)): row for row in rows}


def _endpoint_eval_row(
    spec: dict, raw: dict, via_rows: dict[str, dict] | None
) -> dict | None:
    """二跳端点求值行：有 via 时取经由行，无 via 用本行；找不到经行返回 None。"""
    via = (spec or {}).get("via") if spec else None
    if not via or via_rows is None:
        return raw
    join_value = raw.get(via.get("field", ""))
    if join_value is None:
        return None
    return via_rows.get(str(join_value))


def _lookup_or_stub(
    entity_index: dict,
    namespace: str,
    table: str,
    key: str,
    session: Session,
    gr: GraphRevision,
    key_index: dict[tuple[str, str], str] | None = None,
    ref_entity_type: str | None = None,
) -> str:
    """查已建实体 IRI：优先 (表, 行键) / (类型, 业务键) 索引，找不到建 stub。"""
    key_str = str(key)
    idx = key_index if key_index is not None else {}
    iri = idx.get((table, key_str))
    if iri is None and ref_entity_type:
        iri = idx.get((f"type:{ref_entity_type}", key_str))
    if iri is None:
        # 兼容旧路径：线性扫描（索引未覆盖的历史条目）
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
        idx[(table, key_str)] = iri
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
    table: str,
    row_key: str,
    columns: list[str],
    ev_type: str,
) -> FactEvidence:
    """构造证据行并冻结当时的映射/本体/资源/规则版本。"""
    cfg = run.cfg_snapshot if isinstance(run.cfg_snapshot, dict) else {}
    pins = cfg.get("pins") or {}
    return FactEvidence(
        graph_revision_id=gr.id,
        subject=subject,
        predicate=predicate,
        object_=object_,
        source_id=cfg.get("datasource_id", 0),
        table_name=table,
        row_key=str(row_key),
        columns=list(columns),
        run_id=run.id,
        evidence_type=ev_type,
        mapping_revision_id=pins.get("mapping_revision_id"),
        ontology_revision=pins.get("ontology_revision"),
        resource_revisions=pins.get("resource_versions") or None,
        rule_revisions=pins.get("rule_revisions") or None,
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
    session.flush()  # 先落旧 current=False，避免部分唯一索引冲突
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
    total = session.scalar(select(func.count()).select_from(ExtractionRun)) or 0
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


def list_graph_revisions(
    session: Session, page: int = 1, page_size: int = 50
) -> tuple[list[GraphRevision], int]:
    """列出所有图谱版本（含历史），按发布时间倒序。"""
    stmt = select(GraphRevision).order_by(GraphRevision.published_at.desc())
    total = session.scalar(select(func.count()).select_from(GraphRevision)) or 0
    items = list(
        session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return items, total


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
    session.flush()  # 先落旧 current=False，避免部分唯一索引冲突
    gr.is_current = True
    session.flush()
    return gr


def list_entity_identities(
    session: Session,
    gr_id: int,
    q: str = "",
    page: int = 1,
    page_size: int = 50,
    sort: str = "iri",
) -> tuple[list[EntityIdentity], int]:
    stmt = select(EntityIdentity).where(EntityIdentity.graph_revision_id == gr_id)
    if q:
        stmt = stmt.where(
            EntityIdentity.iri.icontains(q, autoescape=True)
            | EntityIdentity.type_iri.icontains(q, autoescape=True)
            | EntityIdentity.row_key.icontains(q, autoescape=True)
            | EntityIdentity.attrs["name"].as_string().icontains(q, autoescape=True)
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = EntityIdentity.iri.desc() if sort == "-iri" else EntityIdentity.iri.asc()
    items = list(
        session.execute(
            stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)
        ).scalars()
    )
    return items, total


def list_triples(
    session: Session, gr_id: int, subject: str = "", page: int = 1, page_size: int = 50
) -> tuple[list[GraphTriple], int]:
    stmt = select(GraphTriple).where(GraphTriple.graph_revision_id == gr_id)
    if subject:
        stmt = stmt.where(GraphTriple.subject == subject)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars()
    )
    return items, total


def get_evidence(
    session: Session,
    subject: str,
    predicate: str,
    object_: str,
    graph_revision_id: int | None = None,
) -> list[FactEvidence]:
    gr = resolve_graph(session, graph_revision_id)
    return list(
        session.execute(
            select(FactEvidence).where(
                FactEvidence.subject == subject,
                FactEvidence.predicate == predicate,
                FactEvidence.object_ == object_,
                FactEvidence.graph_revision_id == gr.id,
            )
        )
        .scalars()
        .all()
    )


def resolve_graph(
    session: Session, graph_revision_id: int | None = None
) -> GraphRevision:
    """固定到显式结果集；未指定时才解析当前结果集。"""
    gr = (
        session.get(GraphRevision, graph_revision_id)
        if graph_revision_id is not None
        else get_current_graph(session)
    )
    if gr is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"reason": "graph_not_found", "graph_revision_id": graph_revision_id},
        )
    return gr


def get_entity_detail(
    session: Session, iri: str, graph_revision_id: int | None = None
) -> dict:
    """实体详情：属性 + 出边 + 入边 + 派生边 + 证据。"""
    gr = resolve_graph(session, graph_revision_id)
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
