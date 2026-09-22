"""版本化枚举字典管理（M-05）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.governance_common import (
    GovernanceRoute,
    governance_session,
    required_revision,
)
from app.domain import enum_dictionary_service as service
from app.schemas.enum_dictionary import (
    EnumDictionaryInput,
    EnumDictionaryOut,
    EnumDictionaryPage,
    EnumDictionarySort,
    EnumReferenceOut,
)
from app.schemas.response import ApiResponse

router = APIRouter(
    prefix="/governance/enum-dictionaries",
    tags=["governance"],
    route_class=GovernanceRoute,
)
legacy_router = APIRouter(
    prefix="/governance/enums",
    tags=["governance"],
    route_class=GovernanceRoute,
)


@router.get("", response_model=ApiResponse[EnumDictionaryPage])
def list_dictionaries(
    q: str = Query("", max_length=640),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: EnumDictionarySort = "name",
    session: Session = Depends(governance_session),
) -> EnumDictionaryPage:
    items, total = service.list_dictionaries(session, q, page, page_size, sort)
    return EnumDictionaryPage(
        items=[EnumDictionaryOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ApiResponse[EnumDictionaryOut], status_code=201)
def create_dictionary(
    payload: EnumDictionaryInput,
    response: Response,
    session: Session = Depends(governance_session),
) -> EnumDictionaryOut:
    with session.begin():
        result = EnumDictionaryOut.model_validate(
            service.create_dictionary(session, payload)
        )
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.get("/{dictionary_id}", response_model=ApiResponse[EnumDictionaryOut])
def get_dictionary(
    dictionary_id: int,
    response: Response,
    session: Session = Depends(governance_session),
) -> EnumDictionaryOut:
    result = EnumDictionaryOut.model_validate(
        service.get_dictionary(session, dictionary_id)
    )
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.put("/{dictionary_id}", response_model=ApiResponse[EnumDictionaryOut])
def update_dictionary(
    dictionary_id: int,
    payload: EnumDictionaryInput,
    response: Response,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> EnumDictionaryOut:
    with session.begin():
        result = EnumDictionaryOut.model_validate(
            service.update_dictionary(session, dictionary_id, payload, revision)
        )
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.delete("/{dictionary_id}", response_model=ApiResponse[None])
def delete_dictionary(
    dictionary_id: int,
    revision: int = Depends(required_revision),
    session: Session = Depends(governance_session),
) -> None:
    with session.begin():
        service.delete_dictionary(session, dictionary_id, revision)


@router.get(
    "/{dictionary_id}/revisions", response_model=ApiResponse[list[EnumDictionaryOut]]
)
def list_revisions(
    dictionary_id: int, session: Session = Depends(governance_session)
) -> list[EnumDictionaryOut]:
    return service.list_revisions(session, dictionary_id)


@router.get(
    "/{dictionary_id}/references", response_model=ApiResponse[list[EnumReferenceOut]]
)
def list_references(
    dictionary_id: int, session: Session = Depends(governance_session)
) -> list[EnumReferenceOut]:
    return service.list_references(session, dictionary_id)


# Keep the original M-05 contract as a compatibility alias. The canonical
# resource name is /enum-dictionaries; existing clients may still use /enums.
for _path, _endpoint, _methods, _response_model in (
    ("", list_dictionaries, ["GET"], ApiResponse[EnumDictionaryPage]),
    ("", create_dictionary, ["POST"], ApiResponse[EnumDictionaryOut]),
    ("/{dictionary_id}", get_dictionary, ["GET"], ApiResponse[EnumDictionaryOut]),
    ("/{dictionary_id}", update_dictionary, ["PUT"], ApiResponse[EnumDictionaryOut]),
    ("/{dictionary_id}", delete_dictionary, ["DELETE"], ApiResponse[None]),
    (
        "/{dictionary_id}/revisions",
        list_revisions,
        ["GET"],
        ApiResponse[list[EnumDictionaryOut]],
    ),
    (
        "/{dictionary_id}/references",
        list_references,
        ["GET"],
        ApiResponse[list[EnumReferenceOut]],
    ),
):
    legacy_router.add_api_route(
        _path,
        _endpoint,
        methods=_methods,
        response_model=_response_model,
        status_code=201 if _endpoint is create_dictionary else 200,
    )
