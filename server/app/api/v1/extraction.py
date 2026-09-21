"""抽取运行与图谱浏览路由（H-32 / H-33）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.extraction_service import (
    get_current_graph,
    get_entity_detail,
    get_evidence,
    get_run,
    list_entity_identities,
    list_quarantine,
    list_runs,
    list_triples,
    start_run,
    switch_current,
)
from app.schemas.extraction import (
    EntityIdentityOut,
    ExtractionRunOut,
    FactEvidenceOut,
    GraphRevisionOut,
    GraphTripleOut,
    QuarantineOut,
    RunStartRequest,
)

router = APIRouter(prefix="/extraction", tags=["extraction"])


class RunStartResponse(BaseModel):
    run: ExtractionRunOut
    graph_revision: GraphRevisionOut | None


@router.post("/runs", response_model=RunStartResponse, status_code=201)
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


@router.get("/runs", response_model=list[ExtractionRunOut])
def list_all_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[ExtractionRunOut]:
    items, _total = list_runs(session, page, page_size)
    return [ExtractionRunOut.model_validate(i) for i in items]


@router.get("/runs/{run_id}", response_model=ExtractionRunOut)
def get_one_run(
    run_id: int, session: Session = Depends(get_session)
) -> ExtractionRunOut:
    return ExtractionRunOut.model_validate(get_run(session, run_id))


@router.get("/runs/{run_id}/quarantine", response_model=list[QuarantineOut])
def get_run_quarantine(
    run_id: int, session: Session = Depends(get_session)
) -> list[QuarantineOut]:
    return [QuarantineOut.model_validate(q) for q in list_quarantine(session, run_id)]


@router.get("/graph/current", response_model=GraphRevisionOut | None)
def get_current(
    session: Session = Depends(get_session),
) -> GraphRevisionOut | None:
    gr = get_current_graph(session)
    return GraphRevisionOut.model_validate(gr) if gr else None


@router.post("/graph/{graph_revision_id}/switch", response_model=GraphRevisionOut)
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
    response_model=list[EntityIdentityOut],
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


@router.get("/graph/{graph_revision_id}/triples", response_model=list[GraphTripleOut])
def list_graph_triples(
    graph_revision_id: int,
    subject: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[GraphTripleOut]:
    items, _total = list_triples(session, graph_revision_id, subject, page, page_size)
    return [GraphTripleOut.model_validate(i) for i in items]


@router.get("/entities/{iri:path}/detail")
def entity_detail(
    iri: str,
    session: Session = Depends(get_session),
) -> dict:
    """实体详情：属性 + 出边 + 入边 + 派生边 + 证据。"""
    return get_entity_detail(session, iri)


@router.get("/evidence", response_model=list[FactEvidenceOut])
def evidence(
    subject: str = Query(...),
    predicate: str = Query(...),
    object_: str = Query(..., alias="object"),
    session: Session = Depends(get_session),
) -> list[FactEvidenceOut]:
    return [
        FactEvidenceOut.model_validate(e)
        for e in get_evidence(session, subject, predicate, object_)
    ]
