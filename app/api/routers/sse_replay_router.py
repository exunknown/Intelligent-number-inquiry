"""已完成请求的 SSE 短期事件重放接口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from starlette.responses import StreamingResponse

from app.api.dependencies import (
    get_query_audit_repository,
    get_sse_event_repository,
)
from app.entities.auth import QueryPrincipal
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository
from app.repositories.redis.sse_event_repository import SSEEventRepository
from app.security.dependencies import get_query_principal

sse_replay_router = APIRouter()


def _after_sequence(request_id: str, last_event_id: str | None) -> int:
    if not last_event_id:
        return 0
    event_request_id, separator, sequence = last_event_id.rpartition(":")
    if not separator or event_request_id != request_id:
        raise HTTPException(status_code=400, detail="invalid Last-Event-ID")
    try:
        value = int(sequence)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="invalid Last-Event-ID") from error
    if value < 0:
        raise HTTPException(status_code=400, detail="invalid Last-Event-ID")
    return value


@sse_replay_router.get("/api/query/events/{request_id}")
async def replay_query_events_handler(
    request_id: str,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    audit_repository: Annotated[
        QueryAuditRepository, Depends(get_query_audit_repository)
    ] = None,
    event_repository: Annotated[
        SSEEventRepository, Depends(get_sse_event_repository)
    ] = None,
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)] = None,
):
    """重放 TTL 内的已发送帧，不重新执行查询。"""

    if not await audit_repository.has_owned_request(request_id, principal.auth.user_id):
        raise HTTPException(status_code=404, detail="query events not found")
    frames = await event_repository.read_frames(
        request_id, _after_sequence(request_id, last_event_id)
    )
    if not frames:
        raise HTTPException(status_code=404, detail="query events expired")

    async def stream():
        for _, frame in frames:
            yield frame

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
