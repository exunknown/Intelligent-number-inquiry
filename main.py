"""
FastAPI 应用入口

负责创建后端应用实例，注册应用生命周期函数，并把各业务模块中的 router
挂载到同一个 app 上。HTTP 请求会先进入这里创建的 app，再按路由分发到
具体的接口处理函数。
"""

import uuid

from fastapi import FastAPI, Request

from app.api.lifespan import lifespan
from app.api.routers.authz_router import authz_router
from app.api.routers.metric_candidate_router import metric_candidate_router
from app.api.routers.metric_catalog_router import metric_catalog_router
from app.api.routers.query_router import query_router
from app.conf.app_config import app_config
from app.core.context import request_id_ctx_var
from app.core.resource_governance import QueryBodyLimitMiddleware

# lifespan 交给 FastAPI 管理，用于在服务启动和关闭时统一初始化与释放外部客户端
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    QueryBodyLimitMiddleware,
    max_bytes=app_config.resource.max_request_body_bytes,
)

# 把查询路由注册进应用；没有挂载时，/docs 和真实 HTTP 请求都访问不到该接口
app.include_router(query_router)
app.include_router(metric_catalog_router)
app.include_router(metric_candidate_router)
app.include_router(authz_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    # 请求被处理之前
    request_id = uuid.uuid4()
    request_id_ctx_var.set(request_id)
    response = await call_next(request)
    # 请求被处理之后
    return response
