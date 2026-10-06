"""从电商数仓构建并发布业务知识图谱。"""

import argparse
import asyncio

from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.conf.app_config import KnowledgeGraphConfig, app_config
from app.core.log import logger
from app.repositories.mysql.dw.business_graph_repository import (
    BusinessGraphSourceRepository,
)
from app.repositories.mysql.meta.knowledge_graph_repository import (
    KnowledgeGraphRepository,
)
from app.services.business_knowledge_graph_service import (
    BusinessKnowledgeGraphService,
)
from app.services.knowledge_graph_service import GraphBuildResult


async def build_release(
    release_version: str,
    source_repository: BusinessGraphSourceRepository,
    graph_repository: KnowledgeGraphRepository,
    config: KnowledgeGraphConfig,
    *,
    dry_run: bool = False,
) -> GraphBuildResult:
    """构建一个业务图谱版本，并在非 dry-run 模式下替换其落库内容。"""

    if not release_version.strip():
        raise ValueError("release_version must not be empty")

    service = BusinessKnowledgeGraphService(
        source_repository=source_repository,
        config=config,
        repository=graph_repository,
    )
    result = await service.build(release_version)
    if not dry_run:
        await service.persist(result)
    return result


async def build(release_version: str, *, dry_run: bool = False) -> GraphBuildResult:
    """在元数据构建锁内执行一次业务图谱构建。"""

    if not release_version.strip():
        raise ValueError("release_version must not be empty")

    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()
    try:
        from app.scripts.build_meta_knowledge import metadata_build_lock

        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
            metadata_build_lock(meta_mysql_client_manager.engine, release_version),
        ):
            source_repository = BusinessGraphSourceRepository(dw_session)
            graph_repository = KnowledgeGraphRepository(meta_session)
            async with meta_session.begin():
                result = await build_release(
                    release_version,
                    source_repository,
                    graph_repository,
                    app_config.knowledge_graph,
                    dry_run=dry_run,
                )
        logger.info(
            "business knowledge graph built release_version={} node_count={} "
            "edge_count={} dry_run={}",
            release_version,
            result.node_count,
            result.edge_count,
            dry_run,
        )
        return result
    finally:
        await meta_mysql_client_manager.close()
        await dw_mysql_client_manager.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建电商业务聚合知识图谱")
    parser.add_argument("--release-version", required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只构建并校验，不替换 Meta MySQL 中的图谱版本",
    )
    args = parser.parse_args()
    asyncio.run(build(args.release_version, dry_run=args.dry_run))
