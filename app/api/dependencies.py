"""
FastAPI 依赖组装

集中声明 API 层需要的依赖函数，把 Session、Repository、Client 和 Service
按职责组装起来。路由层只通过 Depends 声明自己需要什么对象，具体创建细节
都收敛在这里，避免 HTTP 处理函数直接感知底层基础设施。
"""

from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.cube_client_manager import get_cube_client_manager
from app.clients.embedding_client_manager import get_embedding_client_manager
from app.clients.es_client_manager import get_es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import get_qdrant_client_manager
from app.conf.app_config import app_config
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.metric_candidate_repository import (
    MetricCandidateRepository,
)
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.metric_candidate_service import MetricCandidateService
from app.services.metric_catalog_service import MetricCatalogService
from app.services.query_service import QueryService


async def require_metric_governance_key(
    provided_key: Annotated[str | None, Header(alias="X-Metric-Governance-Key")] = None,
) -> bool:
    """Require the configured management key for governance endpoints."""

    configured_key = app_config.metric_governance.api_key.strip()
    if not configured_key:
        raise HTTPException(
            status_code=503,
            detail="metric governance authentication is not configured",
        )
    if not provided_key or not compare_digest(provided_key, configured_key):
        raise HTTPException(status_code=401, detail="invalid metric governance key")
    return True


async def get_meta_session():
    """创建一次请求内使用的元数据库 Session"""

    # yield 之后的清理逻辑由 async with 负责，FastAPI 会在请求结束后继续执行退出流程
    async with meta_mysql_client_manager.session_factory() as meta_session:
        yield meta_session


async def get_meta_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> MetaMySQLRepository:
    """基于请求级 Session 创建元数据仓储"""

    return MetaMySQLRepository(session)


async def get_query_audit_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> QueryAuditRepository:
    """Create the request-scoped query audit repository."""

    return QueryAuditRepository(session)


async def get_metric_candidate_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> MetricCandidateRepository:
    """Create the request-scoped metric governance candidate repository."""

    return MetricCandidateRepository(session)


async def get_embedding_client() -> HuggingFaceEndpointEmbeddings:
    """获取应用启动阶段初始化好的 Embedding 客户端"""

    return get_embedding_client_manager().client


async def get_dw_session():
    """创建一次请求内使用的数仓 Session"""

    async with dw_mysql_client_manager.session_factory() as dw_session:
        yield dw_session


async def get_dw_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_dw_session)],
) -> DWMySQLRepository:
    """基于请求级 Session 创建数仓仓储"""

    return DWMySQLRepository(session)


async def get_column_qdrant_repository() -> ColumnQdrantRepository:
    """创建字段向量检索仓储"""

    return ColumnQdrantRepository(get_qdrant_client_manager().client)


async def get_metric_qdrant_repository() -> MetricQdrantRepository:
    """创建指标向量检索仓储"""

    return MetricQdrantRepository(get_qdrant_client_manager().client)


async def get_cube_member_qdrant_repository() -> CubeMemberQdrantRepository:
    """创建 Cube 受治理成员向量检索仓储"""

    return CubeMemberQdrantRepository(get_qdrant_client_manager().client)


async def get_metric_catalog_service(
    repository: Annotated[
        CubeMemberQdrantRepository, Depends(get_cube_member_qdrant_repository)
    ],
) -> MetricCatalogService:
    """Create the read-only governed metric catalog service."""

    return MetricCatalogService(repository)


async def get_metric_candidate_service(
    repository: Annotated[
        MetricCandidateRepository, Depends(get_metric_candidate_repository)
    ],
) -> MetricCandidateService:
    """Create the read-only metric governance candidate service."""

    return MetricCandidateService(repository)


async def get_cube_repository() -> CubeRepository:
    """创建 Cube 查询仓储"""

    return CubeRepository(get_cube_client_manager().client, app_config.cube)


async def get_value_es_repository() -> ValueESRepository:
    """创建字段取值全文检索仓储"""

    return ValueESRepository(get_es_client_manager().client)


async def get_query_service(
    meta_mysql_repository: Annotated[
        MetaMySQLRepository, Depends(get_meta_mysql_repository)
    ],
    embedding_client: Annotated[
        HuggingFaceEndpointEmbeddings, Depends(get_embedding_client)
    ],
    dw_mysql_repository: Annotated[DWMySQLRepository, Depends(get_dw_mysql_repository)],
    column_qdrant_repository: Annotated[
        ColumnQdrantRepository, Depends(get_column_qdrant_repository)
    ],
    cube_member_qdrant_repository: Annotated[
        CubeMemberQdrantRepository, Depends(get_cube_member_qdrant_repository)
    ],
    cube_repository: Annotated[CubeRepository, Depends(get_cube_repository)],
    value_es_repository: Annotated[ValueESRepository, Depends(get_value_es_repository)],
    query_audit_repository: Annotated[
        QueryAuditRepository, Depends(get_query_audit_repository)
    ],
    metric_candidate_repository: Annotated[
        MetricCandidateRepository, Depends(get_metric_candidate_repository)
    ],
) -> QueryService:
    """组装一次查询所需的业务服务"""

    # QueryService 只接收已经创建好的依赖对象，本身不关心这些对象来自 MySQL、Qdrant 还是 ES
    return QueryService(
        meta_mysql_repository=meta_mysql_repository,
        embedding_client=embedding_client,
        dw_mysql_repository=dw_mysql_repository,
        column_qdrant_repository=column_qdrant_repository,
        cube_member_qdrant_repository=cube_member_qdrant_repository,
        cube_repository=cube_repository,
        value_es_repository=value_es_repository,
        query_audit_repository=query_audit_repository,
        metric_candidate_repository=metric_candidate_repository,
    )
