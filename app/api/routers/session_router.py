"""查询会话与历史摘要接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.dependencies import (
    get_query_message_repository,
    get_query_session_repository,
)
from app.api.schemas.query_message_schema import QueryMessageResponse
from app.api.schemas.session_schema import (
    QuerySessionCreateRequest,
    QuerySessionDetail,
    QuerySessionMessageResponse,
    QuerySessionSummary,
    QuerySessionUpdateRequest,
)
from app.entities.auth import QueryPrincipal
from app.repositories.mysql.meta.query_message_repository import QueryMessageRepository
from app.repositories.mysql.meta.query_session_repository import QuerySessionRepository
from app.security.dependencies import get_query_principal

session_router = APIRouter()


@session_router.post(
    "/api/sessions", response_model=QuerySessionSummary, status_code=201
)
async def create_session_handler(
    request: QuerySessionCreateRequest,
    repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
) -> QuerySessionSummary:
    session = await repository.create(
        principal.auth.user_id, principal.auth.username, request.title
    )
    return QuerySessionSummary.model_validate(session)


@session_router.get("/api/sessions", response_model=list[QuerySessionSummary])
async def list_sessions_handler(
    repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
) -> list[QuerySessionSummary]:
    sessions = await repository.list_owned(
        principal.auth.user_id,
        limit,
        offset,
        include_archived,
    )
    return [QuerySessionSummary.model_validate(session) for session in sessions]


@session_router.get("/api/sessions/{session_id}", response_model=QuerySessionDetail)
async def get_session_handler(
    session_id: str,
    repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
    message_repository: Annotated[
        QueryMessageRepository, Depends(get_query_message_repository)
    ],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> QuerySessionDetail:
    session = await repository.get_owned(session_id, principal.auth.user_id)
    messages = await message_repository.list_owned_messages(
        session_id,
        principal.auth.user_id,
        limit,
        offset,
    )
    if session is None or messages is None:
        raise HTTPException(status_code=404, detail="query session not found")
    if messages:
        return QuerySessionDetail(
            session=QuerySessionSummary.model_validate(session),
            messages=[
                QueryMessageResponse.model_validate(message) for message in messages
            ],
        )

    legacy_messages = await repository.list_messages(
        session_id,
        principal.auth.user_id,
        limit,
        offset,
    )
    return QuerySessionDetail(
        session=QuerySessionSummary.model_validate(session),
        messages=[
            QuerySessionMessageResponse.model_validate(message)
            for message in legacy_messages or []
        ],
    )


@session_router.patch("/api/sessions/{session_id}", response_model=QuerySessionSummary)
async def update_session_handler(
    session_id: str,
    request: QuerySessionUpdateRequest,
    repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
) -> QuerySessionSummary:
    try:
        session = await repository.update_title(
            session_id,
            principal.auth.user_id,
            request.title,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if session is None:
        raise HTTPException(status_code=404, detail="query session not found")
    return QuerySessionSummary.model_validate(session)


@session_router.post(
    "/api/sessions/{session_id}/archive", response_model=QuerySessionSummary
)
async def archive_session_handler(
    session_id: str,
    repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
) -> QuerySessionSummary:
    session = await repository.set_archived(
        session_id,
        principal.auth.user_id,
        True,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="query session not found")
    return QuerySessionSummary.model_validate(session)


@session_router.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session_handler(
    session_id: str,
    repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
) -> Response:
    deleted = await repository.soft_delete(session_id, principal.auth.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="query session not found")
    return Response(status_code=204)
