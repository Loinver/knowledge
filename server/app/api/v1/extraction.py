"""抽取运行与图谱浏览路由（H-32 / H-33）。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.evidence_service import (
    trace_entity_evidence,
    trace_entity_fusion,
    trace_source_rows,
)
from app.domain.evidence_service import trace_fact as trace_fact_evidence
from app.domain.extraction_service import (
    get_current_graph,
    get_entity_detail,
    get_evidence,
    get_run,
    list_entity_identities,
    list_graph_revisions,
    list_quarantine,
    list_runs,
    list_triples,
    resolve_graph,
    start_run,
    switch_current,
)
from app.domain.extraction_task_service import (
    cancel_task,
    create_task,
    get_task,
    list_tasks,
    live_progress,
)
from app.domain.graph_analysis_service import diff_graph_revisions, shortest_path
from app.domain.graph_recommendation_service import recommend_layouts
from app.domain.graph_view_service import graph_view
from app.domain.run_export_service import export_run
from app.schemas.extraction import (
    EntityDetailOut,
    EntityFusionOut,
    EntityIdentityOut,
    EntityPage,
    EntityTraceOut,
    ExtractionRunExport,
    ExtractionRunOut,
    ExtractionTaskOut,
    FactEvidenceOut,
    FactTraceOut,
    GraphRevisionOut,
    GraphTripleOut,
    GraphViewOut,
    QuarantineOut,
    ReverseTraceOut,
    RunStartRequest,
    TaskCreateRequest,
)
from app.schemas.graph_view import GraphDiffOut, GraphRecommendationOut, PathOut
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/extraction", tags=["extraction"])


@router.get("/graph-view", response_model=ApiResponse[GraphViewOut])
def browse_graph(
    graph_revision_id: int | None = Query(None, ge=1),
    center: str = Query("", max_length=640),
    depth: int = Query(1, ge=1, le=2),
    excluded_types: list[str] = Query(default=[]),
    include_derived: bool = True,
    node_limit: int = Query(200, ge=1, le=500),
    edge_limit: int = Query(1000, ge=1, le=2000),
    session: Session = Depends(get_session),
) -> dict:
    return graph_view(
        session,
        graph_revision_id,
        center,
        depth,
        excluded_types,
        include_derived,
        node_limit,
        edge_limit,
    )


class RunStartResponse(BaseModel):
    run: ExtractionRunOut
    graph_revision: GraphRevisionOut | None


@router.post("/runs", response_model=ApiResponse[RunStartResponse], status_code=201)
def create_run(
    payload: RunStartRequest,
    session: Session = Depends(get_session),
) -> RunStartResponse:
    """启动抽取运行。同步执行四阶段，返回 run + graph_revision。"""
    run = start_run(
        session,
        payload.mapping_revision_id,
        payload.datasource_id,
        payload.namespace,
    )
    session.commit()
    gr = get_current_graph(session)
    return RunStartResponse(
        run=ExtractionRunOut.model_validate(run),
        graph_revision=GraphRevisionOut.model_validate(gr) if gr else None,
    )


@router.post("/tasks", response_model=ApiResponse[ExtractionTaskOut], status_code=202)
def create_extraction_task(
    payload: TaskCreateRequest, session: Session = Depends(get_session)
) -> ExtractionTaskOut:
    """创建异步抽取任务（run_after 为空即调度器尽快执行）。"""
    task = create_task(
        session,
        payload.mapping_revision_id,
        payload.datasource_id,
        payload.namespace,
        incremental=payload.incremental,
        run_after=payload.run_after,
    )
    session.commit()
    return _task_out(task)


def _task_out(task: object) -> ExtractionTaskOut:
    data = ExtractionTaskOut.model_validate(task)
    if data.status == "RUNNING":
        live = live_progress(data.id)
        if live is not None:
            data = data.model_copy(update={"progress": live})
    return data


@router.get("/tasks", response_model=ApiResponse[list[ExtractionTaskOut]])
def list_extraction_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[ExtractionTaskOut]:
    items, _total = list_tasks(session, page, page_size)
    return [_task_out(item) for item in items]


@router.get("/tasks/{task_id}", response_model=ApiResponse[ExtractionTaskOut])
def get_extraction_task(
    task_id: int, session: Session = Depends(get_session)
) -> ExtractionTaskOut:
    return _task_out(get_task(session, task_id))


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse[ExtractionTaskOut])
def cancel_extraction_task(
    task_id: int, session: Session = Depends(get_session)
) -> ExtractionTaskOut:
    """取消任务：PENDING 直接取消；RUNNING 在阶段边界协作生效。"""
    task = cancel_task(session, task_id)
    session.commit()
    return _task_out(task)


@router.get("/runs", response_model=ApiResponse[list[ExtractionRunOut]])
def list_all_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[ExtractionRunOut]:
    items, _total = list_runs(session, page, page_size)
    return [ExtractionRunOut.model_validate(i) for i in items]


@router.get("/runs/{run_id}", response_model=ApiResponse[ExtractionRunOut])
def get_one_run(
    run_id: int, session: Session = Depends(get_session)
) -> ExtractionRunOut:
    return ExtractionRunOut.model_validate(get_run(session, run_id))


@router.get("/runs/{run_id}/export", response_model=ExtractionRunExport)
def download_run_report(
    run_id: int, session: Session = Depends(get_session)
) -> Response:
    """下载运行报告与图谱发布清单；文件响应不套 API 外壳。"""
    report = export_run(session, run_id)
    return Response(
        content=report.model_dump_json(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="run-{run_id}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/runs/{run_id}/quarantine", response_model=ApiResponse[list[QuarantineOut]]
)
def get_run_quarantine(
    run_id: int, session: Session = Depends(get_session)
) -> list[QuarantineOut]:
    return [QuarantineOut.model_validate(q) for q in list_quarantine(session, run_id)]


@router.get("/graph/current", response_model=ApiResponse[GraphRevisionOut | None])
def get_current(
    session: Session = Depends(get_session),
) -> GraphRevisionOut | None:
    gr = get_current_graph(session)
    return GraphRevisionOut.model_validate(gr) if gr else None


@router.get("/graph/revisions", response_model=ApiResponse[list[GraphRevisionOut]])
def list_revisions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[GraphRevisionOut]:
    items, _total = list_graph_revisions(session, page, page_size)
    return [GraphRevisionOut.model_validate(i) for i in items]


@router.post(
    "/graph/{graph_revision_id}/switch", response_model=ApiResponse[GraphRevisionOut]
)
def switch_graph(
    graph_revision_id: int,
    session: Session = Depends(get_session),
) -> GraphRevisionOut:
    """结果集切换：任一历史成功运行可设为当前。"""
    gr = switch_current(session, graph_revision_id)
    session.commit()
    return GraphRevisionOut.model_validate(gr)


@router.get(
    "/graph/{graph_revision_id}/entities",
    response_model=ApiResponse[list[EntityIdentityOut]],
)
def list_entities(
    graph_revision_id: int,
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[EntityIdentityOut]:
    items, _total = list_entity_identities(
        session, graph_revision_id, q, page, page_size
    )
    return [EntityIdentityOut.model_validate(i) for i in items]


@router.get(
    "/graph/{graph_revision_id}/triples",
    response_model=ApiResponse[list[GraphTripleOut]],
)
def list_graph_triples(
    graph_revision_id: int,
    subject: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[GraphTripleOut]:
    items, _total = list_triples(session, graph_revision_id, subject, page, page_size)
    return [GraphTripleOut.model_validate(i) for i in items]


@router.get("/entities", response_model=ApiResponse[EntityPage])
def search_entities(
    graph_revision_id: int | None = Query(None, ge=1),
    q: str = Query("", max_length=640),
    sort: Literal["iri", "-iri"] = "iri",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> EntityPage:
    gr = resolve_graph(session, graph_revision_id)
    items, total = list_entity_identities(session, gr.id, q, page, page_size, sort)
    return EntityPage(
        graph_revision_id=gr.id,
        items=[EntityIdentityOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/entity-detail", response_model=ApiResponse[EntityDetailOut])
@router.get("/entities/{iri:path}/detail", response_model=ApiResponse[EntityDetailOut])
def entity_detail(
    iri: str,
    graph_revision_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
) -> dict:
    """实体详情：属性 + 出边 + 入边 + 派生边 + 证据。"""
    return get_entity_detail(session, iri, graph_revision_id)


@router.get("/evidence", response_model=ApiResponse[list[FactEvidenceOut]])
def evidence(
    subject: str = Query(...),
    predicate: str = Query(...),
    object_: str = Query(..., alias="object"),
    graph_revision_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
) -> list[FactEvidenceOut]:
    return [
        FactEvidenceOut.model_validate(e)
        for e in get_evidence(session, subject, predicate, object_, graph_revision_id)
    ]


@router.get("/evidence/trace", response_model=ApiResponse[FactTraceOut])
def trace_fact(
    subject: str = Query(...),
    predicate: str = Query(...),
    object_: str = Query(..., alias="object"),
    graph_revision_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
) -> dict:
    """从一条事实反查完整追溯链：来源连接/表/行键/字段/运行批次/证据类型。"""
    return trace_fact_evidence(session, subject, predicate, object_, graph_revision_id)


@router.get("/evidence/trace/entity", response_model=ApiResponse[EntityTraceOut])
@router.get(
    "/evidence/trace/entity/{iri:path}", response_model=ApiResponse[EntityTraceOut]
)
def trace_entity(
    iri: str,
    graph_revision_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
) -> dict:
    """实体维度的证据汇总。"""
    return trace_entity_evidence(session, iri, graph_revision_id)


@router.get("/evidence/fusion", response_model=ApiResponse[EntityFusionOut])
@router.get("/evidence/fusion/{iri:path}", response_model=ApiResponse[EntityFusionOut])
def trace_entity_fusion_route(
    iri: str,
    graph_revision_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
) -> dict:
    """实体融合解释（G-29）：来源行贡献与冲突值。"""
    return trace_entity_fusion(session, iri, graph_revision_id)


@router.get("/evidence/trace/reverse", response_model=ApiResponse[ReverseTraceOut])
def trace_reverse(
    source_id: int = Query(..., ge=1),
    table: str = Query(..., max_length=128),
    row_key: str = Query(..., max_length=256),
    graph_revision_id: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
) -> dict:
    """反向追溯：来源行 → 参与的事实与产出实体。"""
    return trace_source_rows(session, source_id, table, row_key, graph_revision_id)


@router.get(
    "/graph/{base_id}/diff/{target_id}", response_model=ApiResponse[GraphDiffOut]
)
def graph_diff(
    base_id: int,
    target_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """两个图谱版本的实体/三元组差异（G-24）。"""
    return diff_graph_revisions(session, base_id, target_id)


@router.get("/graph/{graph_revision_id}/path", response_model=ApiResponse[PathOut])
def graph_path(
    graph_revision_id: int,
    from_: str = Query(..., alias="from", max_length=640),
    to: str = Query(..., max_length=640),
    max_hops: int = Query(3, ge=1, le=6),
    include_derived: bool = True,
    session: Session = Depends(get_session),
) -> dict:
    """有向最短路径（G-12），直接边与派生边可分别参与。"""
    return shortest_path(
        session, graph_revision_id, from_, to, max_hops, include_derived
    )


@router.get(
    "/graph/{graph_revision_id}/layout-recommendations",
    response_model=ApiResponse[GraphRecommendationOut],
)
def graph_layout_recommendations(
    graph_revision_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """从冻结本体快照的语义信号推荐图谱形态（含理由参数）。"""
    return recommend_layouts(session, graph_revision_id)
