"""
FastAPI 依赖组装

集中声明 API 层需要的依赖函数，把 Session、Repository、Client 和 Service
按职责组装起来。路由层只通过 Depends 声明自己需要什么对象，具体创建细节
都收敛在这里，避免 HTTP 处理函数直接感知底层基础设施。
"""

from typing import Annotated

from fastapi import Depends
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.cube_client_manager import get_cube_client_manager
from app.clients.embedding_client_manager import get_embedding_client_manager
from app.clients.es_client_manager import get_es_client_manager
from app.clients.minio_client_manager import get_minio_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
    sql_fallback_mysql_client_manager,
)
from app.clients.qdrant_client_manager import get_qdrant_client_manager
from app.clients.redis_client_manager import get_redis_client_manager
from app.conf.app_config import app_config
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.minio.result_object_store import ResultObjectStore
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.dw.sql_fallback_repository import SQLFallbackRepository
from app.repositories.mysql.meta.app_user_repository import AppUserRepository
from app.repositories.mysql.meta.authz_policy_repository import AuthzPolicyRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.metadata_release_repository import (
    MetadataReleaseRepository,
)
from app.repositories.mysql.meta.metric_candidate_repository import (
    MetricCandidateRepository,
)
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository
from app.repositories.mysql.meta.query_export_repository import QueryExportRepository
from app.repositories.mysql.meta.query_message_repository import QueryMessageRepository
from app.repositories.mysql.meta.query_session_repository import QuerySessionRepository
from app.repositories.mysql.meta.semantic_model_repository import (
    SemanticModelRepository,
)
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.repositories.redis.sse_event_repository import SSEEventRepository
from app.security.sql_policy import SQLPolicyEngine, SQLPolicyLimits
from app.services.application_user_admin_service import ApplicationUserAdminService
from app.services.application_user_service import ApplicationUserService
from app.services.authorization_service import (
    AuthorizationCacheState,
    AuthorizationService,
)
from app.services.cube_semantic_model_compiler import CubeSemanticModelCompiler
from app.services.metadata_release_coordinator import SemanticModelReleaseCoordinator
from app.services.metric_candidate_service import MetricCandidateService
from app.services.metric_catalog_service import MetricCatalogService
from app.services.query_service import QueryService
from app.services.semantic_metric_relation_service import SemanticMetricRelationService
from app.services.semantic_model_release_adapter import SemanticModelReleaseAdapter
from app.services.semantic_model_service import SemanticModelService

_authorization_cache_state = AuthorizationCacheState()
_sql_policy_engine = SQLPolicyEngine(
    SQLPolicyLimits(
        max_sql_bytes=app_config.sql_safety.max_sql_bytes,
        max_ast_nodes=app_config.sql_safety.max_ast_nodes,
        max_nesting_depth=app_config.sql_safety.max_nesting_depth,
        max_ctes=app_config.sql_safety.max_ctes,
        max_union_branches=app_config.sql_safety.max_union_branches,
        max_rows=app_config.sql_safety.max_rows,
    )
)


async def get_meta_session():
    """创建一次请求内使用的元数据库 Session"""

    # yield 之后的清理逻辑由 async with 负责，FastAPI 会在请求结束后继续执行退出流程
    async with meta_mysql_client_manager.session_factory() as meta_session:
        yield meta_session


async def get_query_semantic_model_session():
    """为最佳努力语义快照读取创建隔离的请求级 Session。"""

    async with meta_mysql_client_manager.session_factory() as meta_session:
        yield meta_session


async def get_app_user_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> AppUserRepository:
    """创建请求级应用用户仓储。"""

    return AppUserRepository(session)


async def get_application_user_service(
    repository: Annotated[AppUserRepository, Depends(get_app_user_repository)],
) -> ApplicationUserService:
    """创建请求级应用用户服务。"""

    return ApplicationUserService(repository)


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


async def get_query_session_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> QuerySessionRepository:
    """创建请求级查询会话仓储。"""

    return QuerySessionRepository(session)


async def get_query_message_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> QueryMessageRepository:
    """创建请求级查询消息仓储。"""

    return QueryMessageRepository(session)


async def get_sse_event_repository() -> SSEEventRepository:
    """创建进程级 Redis SSE 事件仓储。"""

    return SSEEventRepository(
        get_redis_client_manager().client,
        app_config.redis,
    )


async def get_query_export_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> QueryExportRepository:
    """创建请求级导出对象归属仓储。"""

    return QueryExportRepository(session)


async def get_result_object_store() -> ResultObjectStore:
    """创建进程级 MinIO 对象存储适配器。"""

    return ResultObjectStore(get_minio_client_manager().client, app_config.minio)


async def get_metadata_release_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> MetadataReleaseRepository:
    """创建请求级元数据发布版本仓储。"""

    return MetadataReleaseRepository(session)


async def get_semantic_model_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> SemanticModelRepository:
    """创建请求级语义模型仓储。"""

    return SemanticModelRepository(session)


async def get_query_semantic_model_repository(
    session: Annotated[AsyncSession, Depends(get_query_semantic_model_session)],
) -> SemanticModelRepository:
    """创建不会污染查询主 Meta Session 的语义快照仓储。"""

    return SemanticModelRepository(session)


async def get_embedding_client() -> HuggingFaceEndpointEmbeddings:
    """获取应用启动阶段初始化好的 Embedding 客户端。"""

    return get_embedding_client_manager().client


async def get_semantic_model_service(
    repository: Annotated[
        SemanticModelRepository, Depends(get_semantic_model_repository)
    ],
    embedding_client: Annotated[
        HuggingFaceEndpointEmbeddings, Depends(get_embedding_client)
    ],
) -> SemanticModelService:
    """组装语义模型治理服务。"""

    metadata_release_repository = MetadataReleaseRepository(repository.session)
    adapter = SemanticModelReleaseAdapter(
        semantic_repository=repository,
        metadata_release_repository=metadata_release_repository,
        qdrant_repository=CubeMemberQdrantRepository(
            get_qdrant_client_manager().client
        ),
        embedding_client=embedding_client,
        compiler=CubeSemanticModelCompiler(
            CubeRepository(
                get_cube_client_manager().client,
                app_config.cube,
            )
        ),
    )
    coordinator = SemanticModelReleaseCoordinator(
        compile_model=adapter.compile_model,
        stage_search_index=adapter.stage_search_index,
        persist_and_activate=adapter.persist_and_activate,
        activate_release=adapter.activate_release,
        rollback_release=adapter.rollback_release,
    )
    return SemanticModelService(repository, release_coordinator=coordinator)


async def get_semantic_metric_relation_service() -> SemanticMetricRelationService:
    """创建请求级无状态指标关系解析器。"""

    return SemanticMetricRelationService()


async def get_authz_policy_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> AuthzPolicyRepository:
    """创建请求级授权策略仓储。"""

    return AuthzPolicyRepository(session)


async def get_authorization_service(
    repository: Annotated[AuthzPolicyRepository, Depends(get_authz_policy_repository)],
) -> AuthorizationService:
    """使用请求级仓储和进程级不可变策略缓存组装授权服务。"""

    return AuthorizationService(repository, cache_state=_authorization_cache_state)


async def get_application_user_admin_service(
    repository: Annotated[AppUserRepository, Depends(get_app_user_repository)],
    policy_repository: Annotated[
        AuthzPolicyRepository, Depends(get_authz_policy_repository)
    ],
    authorization_service: Annotated[
        AuthorizationService, Depends(get_authorization_service)
    ],
) -> ApplicationUserAdminService:
    """组装请求级应用用户管理服务。"""

    return ApplicationUserAdminService(
        repository, policy_repository, authorization_service
    )


async def get_metric_candidate_repository(
    session: Annotated[AsyncSession, Depends(get_meta_session)],
) -> MetricCandidateRepository:
    """Create the request-scoped metric governance candidate repository."""

    return MetricCandidateRepository(session)


async def get_dw_session():
    """创建一次请求内使用的数仓 Session"""

    async with dw_mysql_client_manager.session_factory() as dw_session:
        yield dw_session


async def get_dw_mysql_repository(
    session: Annotated[AsyncSession, Depends(get_dw_session)],
) -> DWMySQLRepository:
    """基于请求级 Session 创建数仓仓储"""

    return DWMySQLRepository(session)


async def get_sql_fallback_session():
    """创建 SQL fallback 专用只读请求 Session。"""

    if not app_config.sql_safety.enabled:
        yield None
        return
    if sql_fallback_mysql_client_manager.session_factory is None:
        raise RuntimeError("SQL fallback database client is not initialized")
    async with sql_fallback_mysql_client_manager.session_factory() as session:
        yield session


async def get_sql_fallback_repository(
    session: Annotated[AsyncSession | None, Depends(get_sql_fallback_session)],
) -> SQLFallbackRepository | None:
    """使用专用只读 Session 创建受限 SQL 执行仓储。"""

    if session is None:
        return None
    return SQLFallbackRepository(session, app_config.sql_safety)


async def get_sql_policy_engine() -> SQLPolicyEngine:
    """获取进程内无状态 SQL AST 策略引擎。"""

    return _sql_policy_engine


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
    semantic_repository: Annotated[
        SemanticModelRepository, Depends(get_semantic_model_repository)
    ],
) -> MetricCatalogService:
    """Create the read-only governed metric catalog service."""

    return MetricCatalogService(repository, semantic_repository)


async def get_metric_candidate_service(
    repository: Annotated[
        MetricCandidateRepository, Depends(get_metric_candidate_repository)
    ],
) -> MetricCandidateService:
    """Create the read-only metric governance candidate service."""

    return MetricCandidateService(repository)


async def get_cube_repository() -> CubeRepository:
    """创建 Cube 查询仓储"""

    return CubeRepository(
        get_cube_client_manager().client,
        app_config.cube,
        max_retries=app_config.resource.dependency_max_retries,
        retry_backoff_seconds=app_config.resource.retry_backoff_seconds,
        circuit_failure_threshold=app_config.resource.circuit_failure_threshold,
        circuit_open_seconds=app_config.resource.circuit_open_seconds,
    )


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
    query_session_repository: Annotated[
        QuerySessionRepository, Depends(get_query_session_repository)
    ],
    query_message_repository: Annotated[
        QueryMessageRepository, Depends(get_query_message_repository)
    ],
    sse_event_repository: Annotated[
        SSEEventRepository, Depends(get_sse_event_repository)
    ],
    query_export_repository: Annotated[
        QueryExportRepository, Depends(get_query_export_repository)
    ],
    result_object_store: Annotated[ResultObjectStore, Depends(get_result_object_store)],
    metadata_release_repository: Annotated[
        MetadataReleaseRepository, Depends(get_metadata_release_repository)
    ],
    semantic_model_repository: Annotated[
        SemanticModelRepository, Depends(get_query_semantic_model_repository)
    ],
    semantic_metric_relation_service: Annotated[
        SemanticMetricRelationService,
        Depends(get_semantic_metric_relation_service),
    ],
    metric_candidate_repository: Annotated[
        MetricCandidateRepository, Depends(get_metric_candidate_repository)
    ],
    sql_fallback_repository: Annotated[
        SQLFallbackRepository | None, Depends(get_sql_fallback_repository)
    ],
    sql_policy_engine: Annotated[SQLPolicyEngine, Depends(get_sql_policy_engine)],
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
        query_session_repository=query_session_repository,
        query_message_repository=query_message_repository,
        sse_event_repository=sse_event_repository,
        query_export_repository=query_export_repository,
        result_object_store=result_object_store,
        metadata_release_repository=metadata_release_repository,
        semantic_model_repository=semantic_model_repository,
        semantic_metric_relation_service=semantic_metric_relation_service,
        metric_candidate_repository=metric_candidate_repository,
        sql_fallback_repository=sql_fallback_repository,
        sql_policy_engine=sql_policy_engine,
    )
