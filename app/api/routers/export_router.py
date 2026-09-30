"""查询结果导出下载接口。"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from app.api.dependencies import get_query_export_repository, get_result_object_store
from app.entities.auth import QueryPrincipal
from app.repositories.minio.result_object_store import ResultObjectStore
from app.repositories.mysql.meta.query_export_repository import QueryExportRepository
from app.security.dependencies import get_query_principal

export_router = APIRouter()


@export_router.get("/api/exports/{export_id}")
async def download_export_handler(
    export_id: str,
    repository: Annotated[QueryExportRepository, Depends(get_query_export_repository)],
    object_store: Annotated[ResultObjectStore, Depends(get_result_object_store)],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
):
    """只允许所属用户在过期前流式读取 MinIO 对象。"""

    export = await repository.get_owned(export_id, principal.auth.user_id)
    if export is None:
        raise HTTPException(status_code=404, detail="result export not found")
    if export.policy_version != principal.permissions.policy_version:
        raise HTTPException(status_code=403, detail="result export permission changed")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if export.expires_at <= now:
        raise HTTPException(status_code=410, detail="result export expired")
    if not await object_store.exists(export.object_key):
        raise HTTPException(status_code=410, detail="result export unavailable")
    return StreamingResponse(
        object_store.iter_object(export.object_key),
        media_type=export.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{export_id}.json"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
