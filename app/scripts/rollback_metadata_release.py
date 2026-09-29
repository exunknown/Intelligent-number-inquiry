"""将元数据 alias 与活动 manifest 回滚到指定已验证版本。"""

import argparse
import asyncio

from app.clients.es_client_manager import get_es_client_manager
from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.clients.qdrant_client_manager import get_qdrant_client_manager
from app.core.log import logger
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.meta.metadata_release_repository import (
    MetadataReleaseRepository,
)
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.scripts.build_meta_knowledge import metadata_build_lock
from app.services.metadata_release_coordinator import (
    MetadataAliasBinding,
    MetadataReleaseCoordinator,
)
from app.services.metadata_release_service import MetadataReleaseService


async def rollback(release_version: str) -> None:
    """校验目标物理资源后，在发布锁内切换 alias 和 manifest。"""

    meta_mysql_client_manager.init()
    get_qdrant_client_manager().init()
    get_es_client_manager().init()
    try:
        async with metadata_build_lock(
            meta_mysql_client_manager.engine, f"rollback:{release_version}"
        ):
            qdrant = get_qdrant_client_manager().client
            column_repository = ColumnQdrantRepository(qdrant)
            metric_repository = MetricQdrantRepository(qdrant)
            cube_repository = CubeMemberQdrantRepository(qdrant)
            value_repository = ValueESRepository(get_es_client_manager().client)

            async with meta_mysql_client_manager.session_factory() as session:
                release_repository = MetadataReleaseRepository(session)
                record = await release_repository.get(release_version)
                if record is None or record["status"] not in {"validated", "active"}:
                    raise ValueError("release version is not validated")
                manifest = record["manifest"]

                qdrant_targets = (
                    manifest.qdrant_column_collection,
                    manifest.qdrant_metric_collection,
                    manifest.qdrant_cube_collection,
                )
                for collection in qdrant_targets:
                    if not await qdrant.collection_exists(collection):
                        raise ValueError(f"Qdrant collection is missing: {collection}")
                if not await value_repository.client.indices.exists(
                    index=manifest.es_value_index
                ):
                    raise ValueError(f"ES index is missing: {manifest.es_value_index}")

                bindings = [
                    MetadataAliasBinding(
                        "column",
                        column_repository,
                        manifest.qdrant_column_collection,
                        await column_repository.get_alias_target(),
                    ),
                    MetadataAliasBinding(
                        "metric",
                        metric_repository,
                        manifest.qdrant_metric_collection,
                        await metric_repository.get_alias_target(),
                    ),
                    MetadataAliasBinding(
                        "cube",
                        cube_repository,
                        manifest.qdrant_cube_collection,
                        await cube_repository.get_alias_target(),
                    ),
                    MetadataAliasBinding(
                        "value",
                        value_repository,
                        manifest.es_value_index,
                        await value_repository.get_alias_target(),
                    ),
                ]
                coordinator = MetadataReleaseCoordinator(
                    MetadataReleaseService(release_repository)
                )
                result = await coordinator.rollback(release_version, bindings)
                logger.info(
                    "metadata release rolled back version={} manifest_sha256={}",
                    result["manifest"].release_version,
                    result["manifest_sha256"],
                )
    finally:
        await meta_mysql_client_manager.close()
        await get_qdrant_client_manager().close()
        await get_es_client_manager().close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    asyncio.run(rollback(args.version))
