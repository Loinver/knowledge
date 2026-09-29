"""本体装配与设计器路由（H-13）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.governance_common import (
    governance_session,
    required_draft_revision,
)
from app.core.db import get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_export_service import export_ontology
from app.domain.ontology_import_service import apply_import, preview_import
from app.domain.ontology_service import (
    add_ref,
    create_ontology,
    delete_ontology,
    detect_conflicts,
    get_canvas_layout,
    get_ontology,
    list_ontologies,
    list_refs,
    list_rules,
    publish_ontology,
    remove_ref,
    update_canvas_layout,
    update_ontology,
)
from app.domain.template_service import get_template
from app.models.domain import Ontology
from app.schemas.ontology import (
    CanvasLayoutOut,
    CanvasLayoutUpdate,
    ConflictInfo,
    OntologyBrief,
    OntologyCreate,
    OntologyExportFormat,
    OntologyOut,
    OntologyRefAdd,
    OntologyRefOut,
    OntologyRuleOut,
    OntologyUpdate,
)
from app.schemas.ontology_import import (
    OntologyImportApplyRequest,
    OntologyImportPreview,
    OntologyImportPreviewRequest,
    OntologyImportResult,
)
from app.schemas.response import ApiResponse
from app.schemas.template import TemplateLink

router = APIRouter(prefix="/ontologies", tags=["ontologies"])


def _out(session: Session, onto: Ontology) -> OntologyOut:
    result = OntologyOut.model_validate(onto)
    if onto.template_id is not None:
        result.template = TemplateLink.model_validate(
            get_template(session, onto.template_id)
        )
    return result


@router.get("", response_model=ApiResponse[list[OntologyBrief]])
def list_onto(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[OntologyBrief]:
    items, _total = list_ontologies(session, q, page, page_size)
    return [OntologyBrief.model_validate(i) for i in items]


@router.post("", response_model=ApiResponse[OntologyOut], status_code=201)
def create_onto_endpoint(
    payload: OntologyCreate, session: Session = Depends(governance_session)
) -> OntologyOut:
    with session.begin():
        onto = create_ontology(session, payload)
        return _out(session, onto)


@router.get("/{ontology_id}", response_model=ApiResponse[OntologyOut])
def get_onto_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> OntologyOut:
    onto = get_ontology(session, ontology_id)
    return _out(session, onto)


@router.put("/{ontology_id}", response_model=ApiResponse[OntologyOut])
def update_onto_endpoint(
    ontology_id: int,
    payload: OntologyUpdate,
    session: Session = Depends(get_session),
) -> OntologyOut:
    onto = get_ontology(session, ontology_id)
    update_ontology(session, onto, payload)
    session.commit()
    return _out(session, onto)


@router.delete("/{ontology_id}", response_model=ApiResponse[None])
def remove_onto_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> None:
    """删除本体；被映射引用一律拒绝，清理 refs/规则引用/修订/画布。"""
    delete_ontology(session, ontology_id)
    session.commit()


@router.get("/{ontology_id}/refs", response_model=ApiResponse[list[OntologyRefOut]])
def list_refs_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> list[OntologyRefOut]:
    refs = list_refs(session, ontology_id)
    return [OntologyRefOut.model_validate(r) for r in refs]


@router.get("/{ontology_id}/rules", response_model=ApiResponse[list[OntologyRuleOut]])
def list_rules_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> list[OntologyRuleOut]:
    return [
        OntologyRuleOut(
            rule_id=rule.id,
            identifier=rule.identifier,
            revision=ref.pinned_revision,
            source_kind=rule.source_kind,
            source_reference=rule.source_reference,
        )
        for rule, ref in list_rules(session, ontology_id)
    ]


@router.post(
    "/{ontology_id}/refs", response_model=ApiResponse[OntologyRefOut], status_code=201
)
def add_ref_endpoint(
    ontology_id: int,
    payload: OntologyRefAdd,
    session: Session = Depends(get_session),
) -> OntologyRefOut:
    ref = add_ref(session, ontology_id, payload)
    session.commit()
    return OntologyRefOut.model_validate(ref)


@router.delete("/{ontology_id}/refs/{ref_id}", response_model=ApiResponse[None])
def remove_ref_endpoint(
    ontology_id: int,
    ref_id: int,
    if_edit_match: int | None = Header(None, ge=0),
    session: Session = Depends(get_session),
) -> None:
    remove_ref(session, ontology_id, ref_id, if_edit_match)
    session.commit()


@router.get("/{ontology_id}/conflicts", response_model=ApiResponse[list[ConflictInfo]])
def conflicts_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> list[ConflictInfo]:
    return detect_conflicts(session, ontology_id)


@router.get("/{ontology_id}/canvas", response_model=ApiResponse[CanvasLayoutOut])
def get_canvas_endpoint(
    ontology_id: int, session: Session = Depends(get_session)
) -> CanvasLayoutOut:
    layout = get_canvas_layout(session, "ontology_designer", ontology_id)
    session.commit()
    return CanvasLayoutOut.model_validate(layout)


@router.put("/{ontology_id}/canvas", response_model=ApiResponse[CanvasLayoutOut])
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
    ontology_id: int,
    if_edit_match: int | None = Header(None, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    onto = get_ontology(session, ontology_id)
    revision = publish_ontology(session, onto, if_edit_match)
    edit_revision = onto.edit_revision
    session.commit()
    return {"revision": revision, "edit_revision": edit_revision}


@router.get(
    "/{ontology_id}/export",
    response_class=Response,
    responses={
        200: {
            "content": {
                "text/turtle": {"schema": {"type": "string"}},
                "application/ld+json": {"schema": {"type": "string"}},
            }
        }
    },
)
def export_onto_endpoint(
    ontology_id: int,
    rdf_format: OntologyExportFormat = Query(
        OntologyExportFormat.TURTLE, alias="format"
    ),
    revision: int | None = Query(None, ge=1),
    session: Session = Depends(get_session),
) -> Response:
    result = export_ontology(session, ontology_id, rdf_format, revision)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.post("/import/preview", response_model=ApiResponse[OntologyImportPreview])
def preview_import_endpoint(
    payload: OntologyImportPreviewRequest,
    session: Session = Depends(governance_session),
) -> OntologyImportPreview:
    return preview_import(session, payload.format, payload.content, payload.ontology_id)


@router.post("/{ontology_id}/import", response_model=ApiResponse[OntologyImportResult])
def apply_import_endpoint(
    ontology_id: int,
    payload: OntologyImportApplyRequest,
    revision: int = Depends(required_draft_revision),
    if_edit_match: int | None = Header(None, ge=0),
    session: Session = Depends(governance_session),
) -> OntologyImportResult:
    if payload.ontology_id != ontology_id:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "ontology_id_mismatch"})
    with session.begin():
        return apply_import(session, payload, revision, if_edit_match=if_edit_match)
