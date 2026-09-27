"""来源证据追溯（H-42）。

每条事实摊平为完整追溯链：
  主体·谓词·客体·来源连接/表/行键/字段·运行批次·证据类型。
从图谱任一三元组反查到 fact_evidence，再补全数据源与运行批次信息。

来源被隔离时（quarantine 命中），前端明确提示"来源记录未进入当前候选图"，
不伪装为证据完整。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.extraction_service import resolve_graph
from app.models.data_access import Datasource
from app.models.extraction import (
    EntityIdentity,
    FactEvidence,
    GraphTriple,
    Quarantine,
)


def trace_fact(
    session: Session,
    subject: str,
    predicate: str,
    object_: str,
    graph_revision_id: int | None = None,
) -> dict:
    """从一条事实（三元组）反查完整追溯链。

    返回摊平结构：
    - fact: { subject, predicate, object }
    - evidences: [{ source_id, source_name, source_kind, table_name,
                    row_key, columns, run_id, evidence_type,
                    quarantined }]
    - quarantined_count: 命中隔离的证据数

    来源被隔离时 quarantined=True，前端提示"未进入当前候选图"。
    """
    gr = resolve_graph(session, graph_revision_id)

    facts = list(
        session.execute(
            select(GraphTriple).where(
                GraphTriple.subject == subject,
                GraphTriple.predicate == predicate,
                GraphTriple.object_ == object_,
                GraphTriple.graph_revision_id == gr.id,
            )
        )
        .scalars()
        .all()
    )
    if not facts:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND,
            {"subject": subject, "predicate": predicate, "object": object_},
        )

    raw_evidences = list(
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

    evidences_out = _flatten_evidence(session, raw_evidences)
    return {
        "graph_revision_id": gr.id,
        "fact": {"subject": subject, "predicate": predicate, "object": object_},
        "evidences": evidences_out,
        "quarantined_count": sum(e["quarantined"] for e in evidences_out),
        "total_count": len(evidences_out),
    }


def trace_entity_evidence(
    session: Session, iri: str, graph_revision_id: int | None = None
) -> dict:
    """实体维度的证据汇总：该实体参与的所有事实的追溯链。"""
    gr = resolve_graph(session, graph_revision_id)

    entity = (
        session.execute(
            select(EntityIdentity).where(
                EntityIdentity.iri == iri,
                EntityIdentity.graph_revision_id == gr.id,
            )
        )
        .scalars()
        .first()
    )
    if entity is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"iri": iri})

    raw_evidences = list(
        session.execute(
            select(FactEvidence).where(
                (FactEvidence.subject == iri) | (FactEvidence.object_ == iri),
                FactEvidence.graph_revision_id == gr.id,
            )
        )
        .scalars()
        .all()
    )

    evidences_out = _flatten_evidence(session, raw_evidences)
    return {
        "graph_revision_id": gr.id,
        "entity": {"iri": iri, "type_iri": entity.type_iri},
        "evidences": evidences_out,
        "total_count": len(evidences_out),
        "quarantined_count": sum(e["quarantined"] for e in evidences_out),
    }


def _flatten_evidence(
    session: Session, raw_evidences: list[FactEvidence]
) -> list[dict]:
    """批量补全来源与同一次运行的隔离标记，不暴露连接参数或凭据。"""
    source_ids = {e.source_id for e in raw_evidences}
    sources = {
        ds.id: ds
        for ds in session.scalars(
            select(Datasource).where(Datasource.id.in_(source_ids))
        )
    }

    run_ids = {e.run_id for e in raw_evidences}
    quarantine_set: set[tuple[int, str, str]] = set()
    if run_ids:
        qs = list(
            session.execute(select(Quarantine).where(Quarantine.run_id.in_(run_ids)))
            .scalars()
            .all()
        )
        quarantine_set = {(q.run_id, q.table_name, q.row_key) for q in qs}

    evidences_out: list[dict] = []
    for ev in raw_evidences:
        ds = sources.get(ev.source_id)
        is_quarantined = (ev.run_id, ev.table_name, ev.row_key) in quarantine_set
        evidences_out.append(
            {
                "id": ev.id,
                "source_id": ev.source_id,
                "source_name": ds.name if ds else None,
                "source_kind": ds.kind if ds else None,
                "table_name": ev.table_name,
                "row_key": ev.row_key,
                "columns": list(ev.columns or []),
                "column_transforms": ev.column_transforms,
                "run_id": ev.run_id,
                "evidence_type": ev.evidence_type,
                "quarantined": is_quarantined,
                "subject": ev.subject,
                "predicate": ev.predicate,
                "object": ev.object_,
                "mapping_revision_id": ev.mapping_revision_id,
                "ontology_revision": ev.ontology_revision,
                "resource_revisions": ev.resource_revisions,
                "rule_revisions": ev.rule_revisions,
            }
        )

    return evidences_out


def trace_source_rows(
    session: Session,
    source_id: int,
    table_name: str,
    row_key: str,
    graph_revision_id: int | None = None,
) -> dict:
    """反向追溯：从来源行反查它参与的事实与产出实体。

    正向链是"事实 → 来源行"；这条反向链让用户从源数据的行出发，
    回答"这一行进了图谱的哪些事实、哪些实体"，满足界面内闭环修正。
    """
    gr = resolve_graph(session, graph_revision_id)
    rows = list(
        session.execute(
            select(FactEvidence).where(
                FactEvidence.graph_revision_id == gr.id,
                FactEvidence.source_id == source_id,
                FactEvidence.table_name == table_name,
                FactEvidence.row_key == row_key,
            )
        )
        .scalars()
        .all()
    )
    ds = session.get(Datasource, source_id)
    facts = [
        {
            "subject": ev.subject,
            "predicate": ev.predicate,
            "object": ev.object_,
            "evidence_id": ev.id,
            "evidence_type": ev.evidence_type,
            "run_id": ev.run_id,
        }
        for ev in rows
    ]
    entities: set[str] = set()
    for ev in rows:
        if ev.predicate == "_entity_attrs":
            entities.add(ev.subject)
        else:
            entities.update((ev.subject, ev.object_))
    return {
        "graph_revision_id": gr.id,
        "source_id": source_id,
        "source_name": ds.name if ds else None,
        "table_name": table_name,
        "row_key": row_key,
        "facts": facts,
        "entities": sorted(entities),
    }
