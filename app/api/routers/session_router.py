"""查询会话与历史摘要接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_query_session_repository
from app.api.schemas.session_schema import (
    QuerySessionCreateRequest,
    QuerySessionDetail,
    QuerySessionMessageResponse,
    QuerySessionSummary,
)
from app.entities.auth import QueryPrincipal
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
) -> list[QuerySessionSummary]:
    sessions = await repository.list_owned(principal.auth.user_id, limit)
    return [QuerySessionSummary.model_validate(session) for session in sessions]


@session_router.get("/api/sessions/{session_id}", response_model=QuerySessionDetail)
async def get_session_handler(
    session_id: str,
    repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
    limit: int = Query(100, ge=1, le=200),
) -> QuerySessionDetail:
    session = await repository.get_owned(session_id, principal.auth.user_id)
    messages = await repository.list_messages(session_id, principal.auth.user_id, limit)
    if session is None or messages is None:
        raise HTTPException(status_code=404, detail="query session not found")
    return QuerySessionDetail(
        session=QuerySessionSummary.model_validate(session),
        messages=[
            QuerySessionMessageResponse.model_validate(message) for message in messages
        ],
    )
