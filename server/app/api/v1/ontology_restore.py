"""完整本体导入预览。授权由应用的业务路由统一提供。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.asset_audit_context import audit_asset, audit_created
from app.core.db import get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_restore_service import inspect_restore, restore_ontology
from app.models.asset_audit import AssetAuditAction, AssetType
from app.schemas.ontology_import import OntologyImportPreviewRequest
from app.schemas.ontology_restore import (
    OntologyRestorePreview,
    OntologyRestoreRequest,
    OntologyRestoreResult,
)
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/ontologies/import", tags=["ontologies"])


@router.post("/restore-preview", response_model=ApiResponse[OntologyRestorePreview])
def preview_restore_endpoint(
    payload: OntologyImportPreviewRequest,
    session: Session = Depends(get_session),
) -> OntologyRestorePreview:
    if payload.ontology_id is not None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "restore_creates_ontology"})
    return inspect_restore(session, payload.format, payload.content)[1]


@router.post("/restore", response_model=ApiResponse[OntologyRestoreResult])
@audit_asset(AssetAuditAction.CREATE, AssetType.ONTOLOGY)
def restore_endpoint(
    payload: OntologyRestoreRequest,
    session: Session = Depends(get_session),
) -> OntologyRestoreResult:
    try:
        result = restore_ontology(session, payload)
        audit_created(session, result.ontology_id)
        session.commit()
        return result
    except IntegrityError as exc:
        session.rollback()
        raise KGError(
            ErrorCode.REVISION_CONFLICT, {"reason": "restore_preview_stale"}
        ) from exc
    except Exception:
        session.rollback()
        raise
