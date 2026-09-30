"""
问数查询接口路由

负责定义前端访问的 `/api/query` 接口，把 HTTP 请求交给 QueryService，
并把问数智能体执行过程以 SSE 形式持续返回给客户端。
路由层只处理请求体、依赖声明和响应类型，不直接创建 Repository 或执行图节点。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from app.api.dependencies import get_query_service, get_query_session_repository
from app.api.schemas.query_schema import QuerySchema
from app.core.query_errors import QueryExecutionError
from app.core.resource_governance import get_resource_admission
from app.entities.auth import QueryPrincipal
from app.repositories.mysql.meta.query_session_repository import QuerySessionRepository
from app.security.dependencies import get_query_principal
from app.services.query_service import QueryService

# 当前模块只维护查询相关接口，避免后续所有 API 都挤在 main.py 中
query_router = APIRouter()


@query_router.post("/api/query")
async def query_handler(
    # 请求体参数：FastAPI 会把前端 JSON 自动解析成 QuerySchema
    query: QuerySchema,
    # 服务依赖：FastAPI 会调用 get_query_service，递归组装它所需的仓储和客户端
    query_service: Annotated[QueryService, Depends(get_query_service)],
    principal: Annotated[QueryPrincipal, Depends(get_query_principal)],
    session_repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
):
    """接收用户自然语言问题，并流式返回 LangGraph 工作流输出"""

    try:
        if query.session_id is not None:
            session = await session_repository.get_owned(
                query.session_id, principal.auth.user_id
            )
            if session is None:
                raise HTTPException(status_code=404, detail="query session not found")
            if session.archived_at is not None:
                raise HTTPException(status_code=409, detail="session_archived")
        lease = await get_resource_admission().acquire(principal.auth.user_id)
    except HTTPException:
        raise
    except QueryExecutionError as error:
        status_code = (
            429
            if error.code
            in {
                "rate_limited",
                "capacity_exhausted",
                "user_capacity_exhausted",
            }
            else 400
        )
        raise HTTPException(status_code=status_code, detail=error.message) from error

    async def stream_events():
        try:
            # query.query 是用户问题字符串；QueryService.query 返回异步生成器供响应逐段消费
            async for chunk in query_service.query(
                query.query,
                principal=principal,
                lease=lease,
                session_id=query.session_id,
            ):
                yield chunk
        finally:
            # 响应在生成器首次迭代前就断开时，QueryService 的 finally 尚未执行，
            # 路由层必须兜底释放已经取得的准入槽。
            await lease.release()

    return StreamingResponse(stream_events(), media_type="text/event-stream")
