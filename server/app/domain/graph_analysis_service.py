"""图谱分析：版本差异（G-24）与关系路径（G-12）。

diff 比较实体内容及直接/派生事实多重集，输出有界的变更清单——超过上限时如实
标记 truncated，不伪装成完整差异。
path 在同一结果集内做有向 BFS，直接边与派生边可分别参与；
找到即返回最短路径（节点 + 边 + 证据定位所需的边 id）。
"""

from __future__ import annotations

import json
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.extraction_service import resolve_graph
from app.models.extraction import (
    DerivedEdge,
    EntityIdentity,
    GraphRevision,
    GraphTriple,
)

MAX_DIFF_ITEMS = 1000
MAX_PATH_HOPS = 6


def diff_graph_revisions(session: Session, base_id: int, target_id: int) -> dict:
    """两个图谱版本的实体/三元组/派生边差异。"""
    base = _require_revision(session, base_id)
    target = _require_revision(session, target_id)
    base_entities = _entity_values(session, base)
    target_entities = _entity_values(session, target)
    base_triples = _fact_counts(session, base)
    target_triples = _fact_counts(session, target)

    entities_added = sorted(target_entities.keys() - base_entities.keys())
    entities_removed = sorted(base_entities.keys() - target_entities.keys())
    entities_modified = [
        {"iri": iri, "before": base_entities[iri], "after": target_entities[iri]}
        for iri in sorted(base_entities.keys() & target_entities.keys())
        if base_entities[iri] != target_entities[iri]
    ]
    triples_added = target_triples - base_triples
    triples_removed = base_triples - target_triples
    return {
        "base_graph_revision_id": base.id,
        "target_graph_revision_id": target.id,
        "entities_added": entities_added[:MAX_DIFF_ITEMS],
        "entities_removed": entities_removed[:MAX_DIFF_ITEMS],
        "entities_modified": entities_modified[:MAX_DIFF_ITEMS],
        "triples_added": _fact_changes(triples_added),
        "triples_removed": _fact_changes(triples_removed),
        "entity_added_count": len(entities_added),
        "entity_removed_count": len(entities_removed),
        "entity_modified_count": len(entities_modified),
        "triple_added_count": sum(triples_added.values()),
        "triple_removed_count": sum(triples_removed.values()),
        "truncated": _truncated(
            [
                len(entities_added),
                len(entities_removed),
                len(entities_modified),
                len(triples_added),
                len(triples_removed),
            ]
        ),
    }


def shortest_path(
    session: Session,
    graph_revision_id: int,
    from_iri: str,
    to_iri: str,
    max_hops: int = 3,
    include_derived: bool = True,
) -> dict:
    """有向最短路径：同一结果集内从 from_iri 到 to_iri 的 BFS。"""
    gr = resolve_graph(session, graph_revision_id)
    if max_hops < 1 or max_hops > MAX_PATH_HOPS:
        max_hops = MAX_PATH_HOPS
    triples = list(
        session.scalars(
            select(GraphTriple).where(
                GraphTriple.graph_revision_id == gr.id,
                GraphTriple.predicate != "_entity_attrs",
            )
        )
    )
    edges: dict[str, list[GraphTriple | DerivedEdge]] = {}
    for t in triples:
        edges.setdefault(t.subject, []).append(t)
    if include_derived:
        derived = list(
            session.scalars(
                select(DerivedEdge).where(DerivedEdge.graph_revision_id == gr.id)
            )
        )
        for d in derived:
            edges.setdefault(d.subject, []).append(d)

    # BFS 记录 (节点, 到达该节点用的边 id, 前驱)
    visited: dict[str, tuple[int | None, str | None]] = {from_iri: (None, None)}

    frontier = [from_iri]
    found = False
    for _hop in range(max_hops):
        next_frontier: list[str] = []
        for node in frontier:
            for edge in edges.get(node, []):
                nxt = edge.object_
                if nxt in visited:
                    continue
                visited[nxt] = (edge.id, node)
                if nxt == to_iri:
                    found = True
                    frontier = []
                    break
                next_frontier.append(nxt)
            if found:
                break
        if found or not next_frontier:
            break
        frontier = next_frontier

    path_nodes: list[str] = []
    path_edge_ids: list[int] = []
    if found:
        cursor: str | None = to_iri
        while cursor is not None:
            path_nodes.append(cursor)
            edge_id, prev = visited[cursor]
            if edge_id is not None:
                path_edge_ids.append(edge_id)
            cursor = prev
        path_nodes.reverse()
        path_edge_ids.reverse()
    return {
        "graph_revision_id": gr.id,
        "from_iri": from_iri,
        "to_iri": to_iri,
        "max_hops": max_hops,
        "found": found,
        "hops": max(0, len(path_nodes) - 1),
        "nodes": path_nodes,
        "edge_ids": path_edge_ids,
    }


def _require_revision(session: Session, graph_revision_id: int) -> GraphRevision:
    gr = session.get(GraphRevision, graph_revision_id)
    if gr is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"graph_revision_id": graph_revision_id}
        )
    return gr


def _entity_values(session: Session, gr: GraphRevision) -> dict[str, dict]:
    return {
        entity.iri: {
            "type_iri": entity.type_iri,
            "row_key": entity.row_key,
            "attrs": entity.attrs,
        }
        for entity in session.scalars(
            select(EntityIdentity).where(EntityIdentity.graph_revision_id == gr.id)
        )
    }


def _fact_counts(session: Session, gr: GraphRevision) -> Counter[str]:
    counts: Counter[str] = Counter()
    rows: list[GraphTriple | DerivedEdge] = list(
        session.scalars(
            select(GraphTriple).where(GraphTriple.graph_revision_id == gr.id)
        )
    )
    rows.extend(
        session.scalars(
            select(DerivedEdge).where(DerivedEdge.graph_revision_id == gr.id)
        )
    )
    for row in rows:
        if row.predicate == "_entity_attrs":
            continue
        value = {
            "subject": row.subject,
            "predicate": row.predicate,
            "object": row.object_,
            "kind": "DERIVED" if isinstance(row, DerivedEdge) else "DIRECT",
            "props": row.props,
        }
        counts[json.dumps(value, sort_keys=True, ensure_ascii=False)] += 1
    return counts


def _fact_changes(counts: Counter[str]) -> list[dict]:
    return [
        {**json.loads(key), "count": counts[key]}
        for key in sorted(counts)[:MAX_DIFF_ITEMS]
    ]


def _truncated(counts: list[int]) -> bool:
    return any(count > MAX_DIFF_ITEMS for count in counts)
