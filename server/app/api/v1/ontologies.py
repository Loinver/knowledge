"""本体装配与设计器路由（H-13）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.ontology_service import (
    add_ref,
    create_ontology,
    detect_conflicts,
    get_canvas_layout,
    get_ontology,
    list_ontologies,
    list_refs,
    publish_ontology,
    remove_ref,
    update_canvas_layout,
    update_ontology,
)
from app.schemas.ontology import (
    CanvasLayoutOut,
    CanvasLayoutUpdate,
    ConflictInfo,
    OntologyBrief,
    OntologyCreate,
    OntologyOut,
    OntologyRefAdd,
    OntologyRefOut,
    OntologyUpdate,
)

router = APIRouter(prefix="/ontologies", tags=["ontologies"])


@router.get("", response_model=list[OntologyBrief])
def list_onto(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[OntologyBrief]:
    items, _total = list_ontologies(session, q, page, page_size)
    return [OntologyBrief.model_validate(i) for i in items]


@router.post("", response_model=OntologyOut, status_code=201)
def create_onto_endpoint(
    payload: OntologyCreate, session: Session = Depends(get_session)
) -> OntologyOut:
    onto = create_ontology(session, payload)
    session.commit()
    return OntologyOut.model_validate(onto)


@router.get("/{ontology_id}", response_model=OntologyOut)
def get_onto_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> OntologyOut:
    onto = get_ontology(session, ontology_id)
    return OntologyOut.model_validate(onto)


@router.put("/{ontology_id}", response_model=OntologyOut)
def update_onto_endpoint(
    ontology_id: int,
    payload: OntologyUpdate,
    session: Session = Depends(get_session),
) -> OntologyOut:
    onto = get_ontology(session, ontology_id)
    update_ontology(session, onto, payload)
    session.commit()
    return OntologyOut.model_validate(onto)


@router.get("/{ontology_id}/refs", response_model=list[OntologyRefOut])
def list_refs_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> list[OntologyRefOut]:
    refs = list_refs(session, ontology_id)
    return [OntologyRefOut.model_validate(r) for r in refs]


@router.post("/{ontology_id}/refs", response_model=OntologyRefOut, status_code=201)
def add_ref_endpoint(
    ontology_id: int,
    payload: OntologyRefAdd,
    session: Session = Depends(get_session),
) -> OntologyRefOut:
    ref = add_ref(session, ontology_id, payload)
    session.commit()
    return OntologyRefOut.model_validate(ref)


@router.delete("/{ontology_id}/refs/{ref_id}", status_code=204)
def remove_ref_endpoint(
    ontology_id: int, ref_id: int, session: Session = Depends(get_session)
) -> None:
    remove_ref(session, ontology_id, ref_id)
    session.commit()


@router.get("/{ontology_id}/conflicts", response_model=list[ConflictInfo])
def conflicts_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> list[ConflictInfo]:
    return detect_conflicts(session, ontology_id)


@router.get("/{ontology_id}/canvas", response_model=CanvasLayoutOut)
def get_canvas_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> CanvasLayoutOut:
    layout = get_canvas_layout(session, "ontology_designer", ontology_id)
    session.commit()
    return CanvasLayoutOut.model_validate(layout)


@router.put("/{ontology_id}/canvas", response_model=CanvasLayoutOut)
def update_canvas_endpoint(
    ontology_id: int,
    payload: CanvasLayoutUpdate,
    session: Session = Depends(get_session),
) -> CanvasLayoutOut:
    layout = update_canvas_layout(
        session, "ontology_designer", ontology_id, payload.positions
    )
    session.commit()
    return CanvasLayoutOut.model_validate(layout)


@router.post("/{ontology_id}/publish")
def publish_onto_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> dict:
    onto = get_ontology(session, ontology_id)
    revision = publish_ontology(session, onto)
    session.commit()
    return {"revision": revision}
