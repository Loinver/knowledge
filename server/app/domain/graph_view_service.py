"""有界的只读图谱视图：过滤先于邻域展开，所有读取固定同一结果集。"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, aliased

from app.domain.extraction_service import resolve_graph
from app.models.extraction import DerivedEdge, EntityIdentity, GraphTriple, Quarantine


def graph_view(
    session: Session,
    graph_revision_id: int | None = None,
    center: str = "",
    depth: int = 1,
    excluded_types: list[str] | None = None,
    include_derived: bool = True,
    node_limit: int = 200,
    edge_limit: int = 1000,
) -> dict:
    """全图含孤立节点；邻域忽略隐藏类型，不把它们当不可见桥梁。

    有界输出明确标记 truncated，不把截断的图伪装成完整结果。
    三元组按数据库 ID 保留，绝不按端点去重业务事实。
    """
    gr = resolve_graph(session, graph_revision_id)
    excluded = excluded_types or []
    node_query = select(EntityIdentity).where(
        EntityIdentity.graph_revision_id == gr.id,
        EntityIdentity.type_iri.not_in(excluded),
    )
    type_counts = [
        {"type_iri": type_iri, "count": count}
        for type_iri, count in session.execute(
            select(EntityIdentity.type_iri, func.count())
            .where(EntityIdentity.graph_revision_id == gr.id)
            .group_by(EntityIdentity.type_iri)
            .order_by(EntityIdentity.type_iri)
        )
    ]
    models: list[type[GraphTriple] | type[DerivedEdge]] = (
        [GraphTriple, DerivedEdge] if include_derived else [GraphTriple]
    )
    source = aliased(EntityIdentity)
    target = aliased(EntityIdentity)

    def edges_between(
        model: type[GraphTriple] | type[DerivedEdge],
    ) -> Select[tuple[int, str, str, str]]:
        return (
            select(
                model.id, model.subject, model.predicate, model.object_.label("object_")
            )
            .join(
                source,
                (source.iri == model.subject) & (source.graph_revision_id == gr.id),
            )
            .join(
                target,
                (target.iri == model.object_) & (target.graph_revision_id == gr.id),
            )
            .where(
                model.graph_revision_id == gr.id,
                source.type_iri.not_in(excluded),
                target.type_iri.not_in(excluded),
            )
            .order_by(model.id)
        )

    truncated = False
    distances: dict[str, int] = {}
    if center:
        root = session.scalar(node_query.where(EntityIdentity.iri == center))
        if root is not None:
            distances[root.iri] = 0
        frontier = set(distances)
        for distance in range(1, depth + 1):
            if not frontier:
                break
            neighbors: set[str] = set()
            for model in models:
                edges = list(
                    session.execute(
                        edges_between(model)
                        .where(
                            model.subject.in_(frontier) | model.object_.in_(frontier)
                        )
                        .limit(edge_limit + 1)
                    )
                )
                truncated |= len(edges) > edge_limit
                for edge in edges[:edge_limit]:
                    neighbors.update((edge.subject, edge.object_))
            candidates = sorted(neighbors - distances.keys())
            remaining = node_limit - len(distances)
            truncated |= len(candidates) > remaining
            frontier = set(candidates[:remaining])
            distances.update(dict.fromkeys(frontier, distance))
        nodes = list(
            session.scalars(
                node_query.where(EntityIdentity.iri.in_(distances)).order_by(
                    EntityIdentity.iri
                )
            )
        )
    else:
        nodes = list(
            session.scalars(
                node_query.order_by(EntityIdentity.iri).limit(node_limit + 1)
            )
        )
        truncated = len(nodes) > node_limit
        nodes = nodes[:node_limit]
    node_iris = [node.iri for node in nodes]
    edges_out: list[dict] = []
    for model in models:
        remaining = edge_limit - len(edges_out)
        edges = list(
            session.execute(
                edges_between(model)
                .where(model.subject.in_(node_iris), model.object_.in_(node_iris))
                .limit(remaining + 1)
            )
        )
        truncated |= len(edges) > remaining
        edges_out.extend(
            {
                "id": edge.id,
                "graph_revision_id": gr.id,
                "subject": edge.subject,
                "predicate": edge.predicate,
                "object_": edge.object_,
                "kind": "DIRECT" if model is GraphTriple else "DERIVED",
            }
            for edge in edges[:remaining]
        )
    return {
        "graph_revision_id": gr.id,
        "nodes": [
            {
                "id": node.id,
                "graph_revision_id": gr.id,
                "iri": node.iri,
                "type_iri": node.type_iri,
                "row_key": node.row_key,
                "attrs": node.attrs,
                "distance": distances.get(node.iri, 0),
            }
            for node in nodes
        ],
        "edges": edges_out,
        "type_counts": type_counts,
        "entity_total": sum(item["count"] for item in type_counts),
        "quarantine_count": session.scalar(
            select(func.count())
            .select_from(Quarantine)
            .where(Quarantine.run_id == gr.run_id)
        )
        or 0,
        "run_id": gr.run_id,
        "truncated": truncated,
    }
