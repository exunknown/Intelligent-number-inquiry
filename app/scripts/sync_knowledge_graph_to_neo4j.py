"""将指定 Meta MySQL 图谱版本显式同步到 Neo4j。"""

import argparse
import asyncio

from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.clients.neo4j_client_manager import get_neo4j_client_manager
from app.conf.app_config import app_config
from app.core.log import logger
from app.repositories.mysql.meta.knowledge_graph_repository import (
    KnowledgeGraphRepository,
)
from app.repositories.neo4j.knowledge_graph_repository import (
    Neo4jKnowledgeGraphRepository,
)
from app.scripts.build_meta_knowledge import metadata_build_lock


async def sync_release(
    release_version: str,
    source_repository: KnowledgeGraphRepository,
    target_repository: Neo4jKnowledgeGraphRepository,
) -> tuple[int, int]:
    """将一个 MySQL 版本完整替换到 Neo4j，并校验目标计数。"""

    if not release_version.strip():
        raise ValueError("release_version must not be empty")
    nodes, edges = await source_repository.list_release(release_version)
    if not nodes:
        raise ValueError(f"source graph release is empty: {release_version}")

    await target_repository.ensure_schema()
    await target_repository.replace_release(release_version, nodes, edges)
    actual_counts = await target_repository.count_release(release_version)
    expected_counts = (len(nodes), len(edges))
    if actual_counts != expected_counts:
        raise RuntimeError(
            "Neo4j graph count mismatch: "
            f"expected={expected_counts}, actual={actual_counts}"
        )
    return actual_counts


async def sync(release_version: str) -> tuple[int, int]:
    """在元数据构建锁内执行一次显式 Neo4j 图谱同步。"""

    if not app_config.neo4j.enabled:
        raise RuntimeError("Neo4j graph sync requires NEO4J_ENABLED=true")

    meta_mysql_client_manager.init()
    neo4j_manager = get_neo4j_client_manager()
    neo4j_manager.init()
    try:
        if neo4j_manager.client is None:
            raise RuntimeError("Neo4j client initialization failed")
        async with metadata_build_lock(
            meta_mysql_client_manager.engine, f"neo4j-sync:{release_version}"
        ):
            async with meta_mysql_client_manager.session_factory() as session:
                source_repository = KnowledgeGraphRepository(session)
                target_repository = Neo4jKnowledgeGraphRepository(
                    neo4j_manager.client,
                    neo4j_manager.database,
                )
                counts = await sync_release(
                    release_version,
                    source_repository,
                    target_repository,
                )
        logger.info(
            "knowledge graph synced to Neo4j release_version={} node_count={} edge_count={}",
            release_version,
            counts[0],
            counts[1],
        )
        return counts
    finally:
        await meta_mysql_client_manager.close()
        await neo4j_manager.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="将指定 Meta MySQL 知识图谱版本同步到 Neo4j"
    )
    parser.add_argument("--release-version", required=True)
    args = parser.parse_args()
    asyncio.run(sync(args.release_version))
