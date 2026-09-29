"""只读检查活动元数据 manifest 与 alias/物理资源是否一致。"""

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
from app.services.metadata_release_consistency import (
    MetadataReleaseConsistencyService,
)
from app.services.metadata_release_coordinator import MetadataAliasBinding


async def check() -> dict:
    """在构建锁内读取活动版本并校验四类 alias。"""

    meta_mysql_client_manager.init()
    get_qdrant_client_manager().init()
    get_es_client_manager().init()
    try:
        async with metadata_build_lock(
            meta_mysql_client_manager.engine, "consistency-check"
        ):
            qdrant = get_qdrant_client_manager().client
            column_repository = ColumnQdrantRepository(qdrant)
            metric_repository = MetricQdrantRepository(qdrant)
            cube_repository = CubeMemberQdrantRepository(qdrant)
            value_repository = ValueESRepository(get_es_client_manager().client)

            async with meta_mysql_client_manager.session_factory() as session:
                repository = MetadataReleaseRepository(session)
                active_version = await repository.get_active_version()
                record = (
                    await repository.get(active_version)
                    if active_version is not None
                    else None
                )
                manifest = record["manifest"] if record is not None else None
                bindings = (
                    [
                        MetadataAliasBinding(
                            "column",
                            column_repository,
                            manifest.qdrant_column_collection,
                            None,
                        ),
                        MetadataAliasBinding(
                            "metric",
                            metric_repository,
                            manifest.qdrant_metric_collection,
                            None,
                        ),
                        MetadataAliasBinding(
                            "cube",
                            cube_repository,
                            manifest.qdrant_cube_collection,
                            None,
                        ),
                        MetadataAliasBinding(
                            "value",
                            value_repository,
                            manifest.es_value_index,
                            None,
                        ),
                    ]
                    if manifest is not None
                    else []
                )

                async def resource_exists(binding: MetadataAliasBinding) -> bool:
                    if binding.label == "value":
                        return await value_repository.client.indices.exists(
                            index=binding.target
                        )
                    return await qdrant.collection_exists(binding.target)

                result = await MetadataReleaseConsistencyService.verify(
                    record,
                    bindings,
                    resource_exists,
                )
                logger.info(
                    "metadata release consistency passed version={} alias_count={}",
                    result["release_version"],
                    result["alias_count"],
                )
                return result
    finally:
        await meta_mysql_client_manager.close()
        await get_qdrant_client_manager().close()
        await get_es_client_manager().close()


if __name__ == "__main__":
    argparse.ArgumentParser(
        description="检查活动元数据 manifest、alias 和物理资源一致性"
    ).parse_args()
    asyncio.run(check())
