"""M-07：从运行快照导出报告，不读取当前映射或数据源连接信息。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.extraction_service import get_run
from app.models.enums import RunResult
from app.models.extraction import GraphRevision
from app.schemas.extraction import ExtractionRunExport, RunPublicationManifest


def export_run(session: Session, run_id: int) -> ExtractionRunExport:
    run = get_run(session, run_id)
    cfg = run.cfg_snapshot if isinstance(run.cfg_snapshot, dict) else {}
    counts = run.counts if isinstance(run.counts, dict) else {}
    publication = None
    if run.finished_at is not None and run.status in (
        RunResult.SUCCESS,
        RunResult.PARTIAL,
    ):
        graph = session.scalars(
            select(GraphRevision).where(
                GraphRevision.run_id == run.id,
                GraphRevision.publishable.is_(True),
            )
        ).one_or_none()
        if graph is not None:
            publication = RunPublicationManifest(
                graph_revision_id=graph.id, published_at=_utc_time(graph.published_at)
            )

    return ExtractionRunExport(
        run_id=run.id,
        mapping_revision_id=run.mapping_revision_id,
        datasource_id=_snapshot_id(cfg.get("datasource_id")),
        ontology_revision=_snapshot_id(cfg.get("onto_version")),
        status=run.status,
        counts={
            key: counts[key]
            for key in (
                "entity_count",
                "triple_count",
                "quarantine_count",
                "evidence_count",
                "derived_edge_count",
            )
            if type(counts.get(key)) is int and counts[key] >= 0
        },
        fingerprint=run.fingerprint,
        started_at=_utc_time(run.started_at),
        finished_at=_utc_time(run.finished_at) if run.finished_at else None,
        publication=publication,
    )


def _snapshot_id(value: object) -> int | None:
    # 遗留快照缺字段时明确未知，禁止使用当前可变配置补齐。
    return value if type(value) is int and value > 0 else None


def _utc_time(value: datetime) -> datetime:
    # SQLite 的 CURRENT_TIMESTAMP 和执行器都写 UTC，但读回时会丢失 tzinfo。
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
