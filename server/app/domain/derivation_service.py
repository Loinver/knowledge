"""抽取阶段4：派生边推导（DERIVATION 规则）。

在本库刚建好的候选图上执行本体钉扎的 AUTO DERIVATION 规则，
产出 DerivedEdge：每条派生边保存产出规则（rule_id）、参与直接事实
（source_fact_ids，指向 GraphTriple.id）与推导产物（props），
使派生事实可以展开到来源事实并给出计算依据。

算子白名单：
- transitive     传递闭包：edge 的可达对派生 derive_edge
- symmetric      对称补边：为 (s,P,o) 补 (o,P,s)，已存在直接边时不补
- co_occurrence  共同邻居：经 via_edge 共享邻居的实体对派生 derive_edge
- product_chain  比例乘积链：沿 edge 路径求 props[attr] 乘积（间接持股）

上限保护：每条规则派生边数封顶（超出即停并只保留已推导部分），
避免闭包爆炸；上限值进运行计数，不静默吞掉。
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.extraction_rule_stage import _load_pinned_auto_rules
from app.models.data_access import MappingRevision
from app.models.extraction import (
    DerivedEdge,
    ExtractionRun,
    GraphRevision,
    GraphTriple,
)

MAX_DERIVED_PER_RULE = 20000


def run_derivation_stage(
    session: Session,
    run: ExtractionRun,
    gr: GraphRevision,
    rev: MappingRevision,
) -> int:
    """执行派生阶段。返回本次写库的派生边总数。"""
    rules = _load_pinned_auto_rules(session, rev)
    derivation_rules = [
        item for item in rules if item[0].language == "DERIVATION" and item[1] is None
    ]
    if not derivation_rules:
        return 0

    triples = list(
        session.scalars(
            select(GraphTriple).where(
                GraphTriple.graph_revision_id == gr.id,
                GraphTriple.predicate != "_entity_attrs",
            )
        )
    )
    derived_count = 0
    existing_spo = {(t.subject, t.predicate, t.object_) for t in triples}
    for rule, _reason in derivation_rules:
        try:
            config = json.loads(rule.expression)
        except ValueError:
            continue
        new_edges = _execute_derivation(config, triples, existing_spo)
        for edge in new_edges[:MAX_DERIVED_PER_RULE]:
            session.add(
                DerivedEdge(
                    graph_revision_id=gr.id,
                    subject=edge["subject"],
                    predicate=edge["predicate"],
                    object_=edge["object"],
                    props=edge.get("props"),
                    rule_id=rule.identifier,
                    source_fact_ids=edge["source_fact_ids"],
                )
            )
            existing_spo.add((edge["subject"], edge["predicate"], edge["object"]))
        derived_count += len(new_edges[:MAX_DERIVED_PER_RULE])
    session.flush()
    return derived_count


def _execute_derivation(
    config: dict, triples: list[GraphTriple], existing_spo: set[tuple[str, str, str]]
) -> list[dict]:
    op = config.get("op")
    if op == "transitive":
        return _op_transitive(config, triples, existing_spo)
    if op == "symmetric":
        return _op_symmetric(config, triples, existing_spo)
    if op == "co_occurrence":
        return _op_co_occurrence(config, triples, existing_spo)
    if op == "product_chain":
        return _op_product_chain(config, triples, existing_spo)
    return []


def _op_transitive(
    config: dict, triples: list[GraphTriple], existing_spo: set[tuple[str, str, str]]
) -> list[dict]:
    """传递闭包：沿 edge 可达的对派生 derive_edge（默认沿用 edge）。"""
    edge = config.get("edge", "")
    derive = config.get("derive_edge", edge)
    if not edge:
        return []
    adj: dict[str, list[GraphTriple]] = {}
    for t in triples:
        if t.predicate == edge:
            adj.setdefault(t.subject, []).append(t)
    out: list[dict] = []
    for start in sorted(adj):
        seen: dict[str, list[int]] = {}
        frontier: list[tuple[str, list[int]]] = [(start, [])]
        visited = {start}
        while frontier:
            node, path = frontier.pop()
            for t in adj.get(node, []):
                nxt = t.object_
                path_ids = [*path, t.id]
                if nxt == start:
                    continue
                seen.setdefault(nxt, path_ids)
                if nxt not in visited:
                    visited.add(nxt)
                    frontier.append((nxt, path_ids))
        for target, path_ids in sorted(seen.items()):
            # derive 沿用 edge 时，直接边已在 existing_spo 中，自动跳过
            if (start, derive, target) in existing_spo:
                continue
            out.append(
                {
                    "subject": start,
                    "predicate": derive,
                    "object": target,
                    "source_fact_ids": path_ids,
                }
            )
    return out


def _op_symmetric(
    config: dict, triples: list[GraphTriple], existing_spo: set[tuple[str, str, str]]
) -> list[dict]:
    """对称补边：为 edge 的每条 (s,P,o) 补 (o,P,s)，直接边已存在时不补。"""
    edge = config.get("edge", "")
    derive = config.get("derive_edge", edge)
    if not edge:
        return []
    out: list[dict] = []
    for t in triples:
        if t.predicate != edge:
            continue
        reverse = (t.object_, derive, t.subject)
        if reverse in existing_spo:
            continue
        out.append(
            {
                "subject": t.object_,
                "predicate": derive,
                "object": t.subject,
                "source_fact_ids": [t.id],
            }
        )
    return out


def _op_co_occurrence(
    config: dict, triples: list[GraphTriple], existing_spo: set[tuple[str, str, str]]
) -> list[dict]:
    """共同参与：经 via_edge 共享邻居的实体对派生 derive_edge（如同事）。"""
    via = config.get("via_edge", "")
    derive = config.get("derive_edge", "")
    if not via or not derive:
        return []
    neighbors: dict[str, set[str]] = {}
    via_triples: dict[tuple[str, str], GraphTriple] = {}
    for t in triples:
        if t.predicate == via:
            neighbors.setdefault(t.subject, set()).add(t.object_)
            neighbors.setdefault(t.object_, set()).add(t.subject)
            via_triples[(t.subject, t.object_)] = t
            via_triples[(t.object_, t.subject)] = t
    out: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for hub in sorted(neighbors):
        members = sorted(neighbors[hub])
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                pair = (a, b) if a <= b else (b, a)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if (pair[0], derive, pair[1]) in existing_spo:
                    continue
                via_a = via_triples.get((pair[0], hub))
                via_b = via_triples.get((pair[1], hub))
                fact_ids = [t.id for t in (via_a, via_b) if t is not None]
                out.append(
                    {
                        "subject": pair[0],
                        "predicate": derive,
                        "object": pair[1],
                        "source_fact_ids": fact_ids,
                        "props": {"via": hub} if hub else None,
                    }
                )
    return out


def _op_product_chain(
    config: dict, triples: list[GraphTriple], existing_spo: set[tuple[str, str, str]]
) -> list[dict]:
    """比例乘积链：沿 edge 路径（长度 ≥2）求 props[attr] 乘积，派生间接持股。"""
    edge = config.get("edge", "")
    attr = config.get("attr", "")
    derive = config.get("derive_edge", "indirectlyHolds")
    minimum = float(config.get("min_value", 0))
    max_hops = int(config.get("max_hops", 5))
    if not edge or not attr:
        return []
    adj: dict[str, list[tuple[GraphTriple, float]]] = {}
    for t in triples:
        if t.predicate == edge:
            value = (t.props or {}).get(attr)
            if not isinstance(value, int | float):
                continue
            adj.setdefault(t.subject, []).append((t, float(value) / 100.0))
    out: list[dict] = []
    # 逐层扩展：paths[node] = [(start, product, fact_ids)]
    frontier: dict[str, list[tuple[str, float, list[int]]]] = {}
    for node, edges in adj.items():
        for t, weight in edges:
            frontier.setdefault(t.object_, []).append((node, weight, [t.id]))
    derived_pairs: set[tuple[str, str]] = set()
    for _hop in range(1, max_hops):
        next_frontier: dict[str, list[tuple[str, float, list[int]]]] = {}
        for target, entries in sorted(frontier.items()):
            for start, product, fact_ids in entries:
                for t, weight in adj.get(target, []):
                    nxt = t.object_
                    if nxt == start:
                        continue
                    new_product = product * weight
                    new_ids = [*fact_ids, t.id]
                    pair = (start, nxt)
                    if pair not in derived_pairs and new_product > minimum:
                        derived_pairs.add(pair)
                        if (start, derive, nxt) not in existing_spo:
                            out.append(
                                {
                                    "subject": start,
                                    "predicate": derive,
                                    "object": nxt,
                                    "source_fact_ids": new_ids,
                                    "props": {attr: round(new_product * 100.0, 6)},
                                }
                            )
                    next_frontier.setdefault(nxt, []).append(
                        (start, new_product, new_ids)
                    )
        frontier = next_frontier
        if not frontier:
            break
    return out
