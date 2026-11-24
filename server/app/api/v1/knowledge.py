"""Knowledge persistence endpoints; global business authorization is inherited."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import current_user
from app.core.db import get_session
from app.domain import knowledge_service as service
from app.domain.knowledge_parser import MAX_FILE_BYTES
from app.models.account import User
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBasePage,
    KnowledgeBaseUpdate,
    KnowledgeDocumentOut,
    KnowledgeDocumentPage,
    KnowledgeTaskPage,
)
from app.schemas.response import ApiResponse

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge"])


@router.get("", response_model=ApiResponse[KnowledgeBasePage])
def list_bases(
    q: str = Query("", max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("-updated_at"),
    status: service.ArchiveFilter = Query("active"),
    session: Session = Depends(get_session),
) -> KnowledgeBasePage:
    bases, total = service.list_bases(session, q, page, page_size, sort, status)
    return KnowledgeBasePage(
        items=[service.base_out(session, base) for base in bases],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ApiResponse[KnowledgeBaseOut], status_code=201)
def create_base(
    payload: KnowledgeBaseCreate,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> KnowledgeBaseOut:
    base = service.create_base(session, payload, user.id)
    result = service.base_out(session, base)
    session.commit()
    return result


@router.get("/{kb_id}", response_model=ApiResponse[KnowledgeBaseOut])
def get_base(kb_id: int, session: Session = Depends(get_session)) -> KnowledgeBaseOut:
    return service.base_out(session, service.get_base(session, kb_id))


@router.put("/{kb_id}", response_model=ApiResponse[KnowledgeBaseOut])
def edit_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    if_match: int = Header(..., ge=1),
    session: Session = Depends(get_session),
) -> KnowledgeBaseOut:
    result = service.base_out(
        session, service.edit_base(session, kb_id, payload, if_match)
    )
    session.commit()
    return result


@router.post("/{kb_id}/archive", response_model=ApiResponse[KnowledgeBaseOut])
def archive_base(
    kb_id: int,
    if_match: int = Header(..., ge=1),
    session: Session = Depends(get_session),
) -> KnowledgeBaseOut:
    result = service.base_out(
        session, service.set_base_archived(session, kb_id, True, if_match)
    )
    session.commit()
    return result


@router.post("/{kb_id}/restore", response_model=ApiResponse[KnowledgeBaseOut])
def restore_base(
    kb_id: int,
    if_match: int = Header(..., ge=1),
    session: Session = Depends(get_session),
) -> KnowledgeBaseOut:
    result = service.base_out(
        session, service.set_base_archived(session, kb_id, False, if_match)
    )
    session.commit()
    return result


@router.get("/{kb_id}/documents", response_model=ApiResponse[KnowledgeDocumentPage])
def list_documents(
    kb_id: int,
    q: str = Query("", max_length=255),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("-created_at"),
    status: service.ArchiveFilter = Query("active"),
    session: Session = Depends(get_session),
) -> KnowledgeDocumentPage:
    documents, total = service.list_documents(
        session, kb_id, q, page, page_size, sort, status
    )
    return KnowledgeDocumentPage(
        items=[service.document_out(session, doc) for doc in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{kb_id}/documents",
    response_model=ApiResponse[KnowledgeDocumentOut],
    status_code=201,
)
async def upload_document(
    kb_id: int,
    request: Request,
    filename: str = Query(..., max_length=1024),
    content_type: str | None = Query(None, max_length=200),
    session: Session = Depends(get_session),
) -> KnowledgeDocumentOut:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/octet-stream"
    ):
        raise service.invalid("knowledge_upload_requires_octet_stream")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError as exc:
            raise service.invalid("knowledge_invalid_content_length") from exc
        if size > MAX_FILE_BYTES:
            raise service.invalid("knowledge_file_too_large", limit=MAX_FILE_BYTES)
    content = bytearray()
    async for part in request.stream():
        if len(content) + len(part) > MAX_FILE_BYTES:
            raise service.invalid("knowledge_file_too_large", limit=MAX_FILE_BYTES)
        content.extend(part)
    result = service.upload_document(
        session, kb_id, filename, content_type, bytes(content)
    )
    session.commit()
    return result


@router.get(
    "/{kb_id}/documents/{document_id}", response_model=ApiResponse[KnowledgeDocumentOut]
)
def get_document(
    kb_id: int, document_id: str, session: Session = Depends(get_session)
) -> KnowledgeDocumentOut:
    return service.document_out(
        session, service.get_document(session, kb_id, document_id)
    )


@router.post(
    "/{kb_id}/documents/{document_id}/reprocess",
    response_model=ApiResponse[KnowledgeDocumentOut],
)
def reprocess_document(
    kb_id: int,
    document_id: str,
    if_match: int = Header(..., ge=1),
    session: Session = Depends(get_session),
) -> KnowledgeDocumentOut:
    result = service.document_out(
        session, service.queue_document(session, kb_id, document_id, if_match)
    )
    session.commit()
    return result


@router.post(
    "/{kb_id}/documents/{document_id}/archive",
    response_model=ApiResponse[KnowledgeDocumentOut],
)
def archive_document(
    kb_id: int,
    document_id: str,
    if_match: int = Header(..., ge=1),
    session: Session = Depends(get_session),
) -> KnowledgeDocumentOut:
    result = service.document_out(
        session,
        service.set_document_archived(session, kb_id, document_id, True, if_match),
    )
    session.commit()
    return result


@router.post(
    "/{kb_id}/documents/{document_id}/restore",
    response_model=ApiResponse[KnowledgeDocumentOut],
)
def restore_document(
    kb_id: int,
    document_id: str,
    if_match: int = Header(..., ge=1),
    session: Session = Depends(get_session),
) -> KnowledgeDocumentOut:
    result = service.document_out(
        session,
        service.set_document_archived(session, kb_id, document_id, False, if_match),
    )
    session.commit()
    return result


@router.get(
    "/{kb_id}/documents/{document_id}/tasks",
    response_model=ApiResponse[KnowledgeTaskPage],
)
def list_tasks(
    kb_id: int,
    document_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> KnowledgeTaskPage:
    tasks, total = service.list_tasks(session, kb_id, document_id, page, page_size)
    return KnowledgeTaskPage(
        items=[service.task_out(task) for task in tasks],
        total=total,
        page=page,
        page_size=page_size,
    )
