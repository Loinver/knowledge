"""抽取阶段3：规则校验（H-32 第 3 阶段的独立实现）。

对本次运行刚建好的候选图执行：
1. 实例层校验（I01–I06），落 ValidationReport(scope="instance")；
2. 本体钉扎的 AUTO DATA 规则（算子白名单：无环/合计上限/唯一键/必备端点/日期格式），
   命中写隔离并保留命中焦点与来源行；
3. SHACL/OWL 的 AUTO 规则不在管线执行范围，如实记 NOT_RUN——未执行绝不冒充通过。

版本完整性：规则的当前 revision 与本体发布时的 pinned_revision 不一致
（规则在发布后被改过）时不执行，记 NOT_RUN；钉扎版本必须可追溯。
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.instance_validation_service import run_instance_validation
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import OntologyRuleRef
from app.models.enums import ValidationState
from app.models.extraction import (
    EntityIdentity,
    ExtractionRun,
    FactEvidence,
    GraphRevision,
    GraphTriple,
    Quarantine,
)
from app.models.governance import Rule

MAX_HITS_PER_RULE = 200


def run_rule_stage(
    session: Session,
    run: ExtractionRun,
    gr: GraphRevision,
    rev: MappingRevision,
) -> dict:
    """执行规则阶段。返回计数与逐规则结果（进 run.counts）。"""
    rules = _load_pinned_auto_rules(session, rev)
    rule_results: list[dict] = []

    triples = list(
        session.scalars(
            select(GraphTriple).where(
                GraphTriple.graph_revision_id == gr.id,
                GraphTriple.predicate != "_entity_attrs",
            )
        )
    )
    entities = list(
        session.scalars(
            select(EntityIdentity).where(EntityIdentity.graph_revision_id == gr.id)
        )
    )
    namespace = ""
    if isinstance(run.cfg_snapshot, dict):
        namespace = str(run.cfg_snapshot.get("namespace", ""))

    quarantined_by_rule = 0
    rule_violation_count = 0
    for rule, not_run_reason in rules:
        # DERIVATION 规则在阶段 4 执行，结果计入派生边，不在本阶段重复执行
        if rule.language != "DATA":
            continue
        if not_run_reason is not None:
            rule_results.append(
                {
                    "rule_id": rule.identifier,
                    "language": rule.language,
                    "state": ValidationState.NOT_RUN.value,
                    "hits": 0,
                    "reason": not_run_reason,
                }
            )
            continue
        result = _execute_data_rule(
            session, run, gr, rule, triples, entities, namespace
        )
        rule_results.append(result)
        if result["state"] == ValidationState.VIOLATION.value:
            rule_violation_count += result["hits"]
            quarantined_by_rule += result["quarantined"]

    report = run_instance_validation(session, gr.id)
    return {
        "quarantined_by_rule": quarantined_by_rule,
        "rule_violation_count": rule_violation_count,
        "validation_summary": report.summary,
        "rule_results": rule_results,
    }


def _load_pinned_auto_rules(
    session: Session, rev: MappingRevision
) -> list[tuple[Rule, str | None]]:
    """载入本体钉扎的 AUTO 规则。

    返回 (rule, not_run_reason)：reason 为 None 表示可执行；否则给出如实的
    未执行原因（语言不在管线范围 / 规则在发布后被改过）。
    """
    mapping = session.get(Mapping, rev.mapping_id)
    if mapping is None:
        return []
    rows = session.execute(
        select(OntologyRuleRef, Rule)
        .join(Rule, Rule.id == OntologyRuleRef.rule_id)
        .where(OntologyRuleRef.ontology_id == mapping.ontology_id)
        .order_by(Rule.identifier)
    ).all()
    out: list[tuple[Rule, str | None]] = []
    for ref, rule in rows:
        if rule.execution != "AUTO":
            continue
        if rule.language not in ("DATA", "DERIVATION"):
            out.append((rule, "language_not_executed_in_pipeline"))
            continue
        if rule.revision != ref.pinned_revision:
            out.append((rule, "rule_changed_after_pin"))
            continue
        out.append((rule, None))
    return out


def _execute_data_rule(
    session: Session,
    run: ExtractionRun,
    gr: GraphRevision,
    rule: Rule,
    triples: list[GraphTriple],
    entities: list[EntityIdentity],
    namespace: str,
) -> dict:
    """执行一条 DATA 规则。返回四态结果 + 命中数 + 隔离写入数。"""
    try:
        config = json.loads(rule.expression)
    except ValueError:
        return {
            "rule_id": rule.identifier,
            "language": rule.language,
            "state": ValidationState.NOT_RUN.value,
            "hits": 0,
            "reason": "invalid_rule_expression",
        }
    op = config.get("op")
    if op == "acyclic":
        hits = _op_acyclic(triples, config)
    elif op == "sum_le":
        hits = _op_sum_le(triples, config)
    elif op == "unique_attr":
        hits = _op_unique_attr(entities, namespace, config)
    elif op == "required_edge":
        hits = _op_required_edge(triples, entities, namespace, config)
    elif op == "date_format":
        hits = _op_date_format(entities, config)
    else:
        return {
            "rule_id": rule.identifier,
            "language": rule.language,
            "state": ValidationState.NOT_RUN.value,
            "hits": 0,
            "reason": "unknown_data_op",
        }
    state = ValidationState.VIOLATION if hits else ValidationState.PASS
    quarantined = 0
    if hits:
        quarantined = _quarantine_hits(session, run, gr, rule, op, hits)
    return {
        "rule_id": rule.identifier,
        "language": rule.language,
        "state": state.value,
        "hits": len(hits),
        "quarantined": quarantined,
        "truncated": len(hits) > MAX_HITS_PER_RULE,
    }


def _hit(focus: str, detail: dict, triple_ids: list[int] | None = None) -> dict:
    """一次命中：焦点（实体 IRI 或分组键）+ 结构化明细 + 涉及三元组。"""
    return {
        "focus": focus,
        "detail": detail,
        "triple_ids": triple_ids or [],
    }


def _op_acyclic(triples: list[GraphTriple], config: dict) -> list[dict]:
    """无环检查：predicate == edge 的边构成的图不得有环。"""
    edge = config.get("edge", "")
    adj: dict[str, list[GraphTriple]] = {}
    for t in triples:
        if t.predicate == edge:
            adj.setdefault(t.subject, []).append(t)
    state: dict[str, int] = {}
    stack: list[GraphTriple] = []
    hits: list[dict] = []

    def dfs(node: str) -> None:
        state[node] = 1
        for t in adj.get(node, []):
            stack.append(t)
            nxt = t.object_
            if state.get(nxt) == 1:
                hits.append(
                    _hit(
                        nxt,
                        {"cycle": [t.subject, t.object_], "edge": edge},
                        [item.id for item in stack],
                    )
                )
            elif state.get(nxt, 0) == 0:
                dfs(nxt)
            stack.pop()
        state[node] = 2

    for node in list(adj):
        if state.get(node, 0) == 0:
            dfs(node)
    return hits


def _op_sum_le(triples: list[GraphTriple], config: dict) -> list[dict]:
    """合计上限：edge 的边按 group 端分组求 props[attr] 之和不得超过 max。"""
    edge = config.get("edge", "")
    attr = config.get("attr", "")
    maximum = float(config.get("max", 100))
    group = config.get("group", "object")
    groups: dict[str, list[GraphTriple]] = {}
    for t in triples:
        if t.predicate != edge:
            continue
        key = t.object_ if group == "object" else t.subject
        if t.props and attr in t.props:
            groups.setdefault(key, []).append(t)
    hits: list[dict] = []
    for key in sorted(groups):
        members = groups[key]
        total = 0.0
        for t in members:
            value = (t.props or {}).get(attr)
            if isinstance(value, int | float):
                total += float(value)
        if total > maximum:
            hits.append(
                _hit(
                    key,
                    {"sum": total, "max": maximum, "attr": attr, "group": group},
                    [t.id for t in members],
                )
            )
    return hits


def _op_unique_attr(
    entities: list[EntityIdentity], namespace: str, config: dict
) -> list[dict]:
    """唯一键：同类型实体的某属性值不得重复（如统一社会信用代码）。"""
    type_name = config.get("type", "")
    attr = config.get("attr", "")
    seen: dict[str, list[EntityIdentity]] = {}
    for e in entities:
        if not _type_matches(e.type_iri, type_name, namespace):
            continue
        value = (e.attrs or {}).get(attr)
        if value is None or value == "":
            continue
        seen.setdefault(str(value), []).append(e)
    hits: list[dict] = []
    for value in sorted(seen):
        group = seen[value]
        if len(group) > 1:
            hits.append(
                _hit(
                    group[0].iri,
                    {"attr": attr, "value": value, "iris": [e.iri for e in group]},
                )
            )
    return hits


def _op_required_edge(
    triples: list[GraphTriple],
    entities: list[EntityIdentity],
    namespace: str,
    config: dict,
) -> list[dict]:
    """必备端点：type 的每个实体至少要有 min 条 predicate == edge 的出边。"""
    edge = config.get("edge", "")
    type_name = config.get("type", "")
    minimum = int(config.get("min", 1))
    counts: dict[str, int] = {}
    for t in triples:
        if t.predicate == edge:
            counts[t.subject] = counts.get(t.subject, 0) + 1
    hits: list[dict] = []
    for e in entities:
        if not _type_matches(e.type_iri, type_name, namespace):
            continue
        if counts.get(e.iri, 0) < minimum:
            hits.append(
                _hit(
                    e.iri,
                    {"edge": edge, "count": counts.get(e.iri, 0), "min": minimum},
                )
            )
    return hits


def _op_date_format(entities: list[EntityIdentity], config: dict) -> list[dict]:
    """日期格式：实体属性值必须符合指定 strptime 格式（YYYYMMDD → %Y%m%d）。"""
    attr = config.get("attr", "")
    fmt = str(config.get("format", "%Y-%m-%d"))
    if fmt.upper() == "YYYYMMDD":
        fmt = "%Y%m%d"
    hits: list[dict] = []
    for e in entities:
        value = (e.attrs or {}).get(attr)
        if value is None or value == "":
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            try:
                datetime.strptime(str(item), fmt)
            except ValueError:
                hits.append(
                    _hit(e.iri, {"attr": attr, "value": str(item), "format": fmt})
                )
    return hits


def _type_matches(type_iri: str, type_name: str, namespace: str) -> bool:
    """类型匹配：支持完整 IRI 或本地名（namespace + name 的后缀匹配）。"""
    if not type_name:
        return False
    if type_iri == type_name or (namespace and type_iri == f"{namespace}{type_name}"):
        return True
    return type_iri.endswith(f"/{type_name}")


def _quarantine_hits(
    session: Session,
    run: ExtractionRun,
    gr: GraphRevision,
    rule: Rule,
    op: str,
    hits: list[dict],
) -> int:
    """把命中写进隔离：经命中三元组或焦点实体反查证据行定位（表, 行键）。"""
    triple_ids = {tid for hit in hits for tid in hit["triple_ids"]}
    focus_iris = {hit["focus"] for hit in hits if hit["focus"].startswith("http")}
    rows: list[FactEvidence] = []
    if triple_ids:
        triples = list(
            session.scalars(select(GraphTriple).where(GraphTriple.id.in_(triple_ids)))
        )
        for t in triples:
            rows.extend(
                session.scalars(
                    select(FactEvidence).where(
                        FactEvidence.graph_revision_id == gr.id,
                        FactEvidence.subject == t.subject,
                        FactEvidence.predicate == t.predicate,
                        FactEvidence.object_ == t.object_,
                    )
                )
            )
    if focus_iris:
        rows.extend(
            session.scalars(
                select(FactEvidence).where(
                    FactEvidence.graph_revision_id == gr.id,
                    FactEvidence.subject.in_(focus_iris),
                )
            )
        )
    seen: set[tuple[str, str]] = set()
    count = 0
    for ev in rows:
        key = (ev.table_name, ev.row_key)
        if key in seen:
            continue
        seen.add(key)
        session.add(
            Quarantine(
                run_id=run.id,
                table_name=ev.table_name,
                row_key=ev.row_key,
                field=op,
                raw_value=rule.identifier,
                transform_chain=["rule_stage", op],
                rule_id=rule.identifier,
            )
        )
        count += 1
    session.flush()
    return count
