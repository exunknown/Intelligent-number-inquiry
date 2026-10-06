"""校验并激活一次元数据 manifest。"""

import argparse
import asyncio
import hashlib
import inspect
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from app.clients.cube_client_manager import get_cube_client_manager
from app.clients.embedding_client_manager import get_embedding_client_manager
from app.clients.es_client_manager import get_es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import get_qdrant_client_manager
from app.conf.app_config import app_config
from app.core.log import logger
from app.entities.metadata_release import MetadataReleaseManifest
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.knowledge_graph_repository import (
    KnowledgeGraphRepository,
)
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.metadata_release_repository import (
    MetadataReleaseRepository,
)
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.scripts.build_meta_knowledge import metadata_build_lock
from app.services.knowledge_graph_service import KnowledgeGraphService
from app.services.meta_knowledge_service import MetaKnowledgeService
from app.services.metadata_release_coordinator import (
    MetadataAliasBinding,
    MetadataReleaseCoordinator,
)
from app.services.metadata_release_service import MetadataReleaseService


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prompt_version(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "prompts").glob("*.prompt")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _app_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)["project"]["version"]


async def _close_embedding_client() -> None:
    """关闭 HuggingFace Embedding 内部 HTTP 客户端。"""

    manager = get_embedding_client_manager()
    client = manager.client
    if client is None:
        return
    for attribute in ("async_client", "client"):
        inner_client = getattr(client, attribute, None)
        close = getattr(inner_client, "aclose", None) or getattr(
            inner_client, "close", None
        )
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result
    manager.client = None


async def _build_staging(config_path: Path, release_version: str):
    """在当前发布锁内构建并校验 staging，不切换线上 alias。"""

    async with (
        meta_mysql_client_manager.session_factory() as meta_session,
        dw_mysql_client_manager.session_factory() as dw_session,
    ):
        meta_mysql_repository = MetaMySQLRepository(meta_session)
        service = MetaKnowledgeService(
            meta_mysql_repository=meta_mysql_repository,
            dw_mysql_repository=DWMySQLRepository(dw_session),
            column_qdrant_repository=ColumnQdrantRepository(
                get_qdrant_client_manager().client
            ),
            embedding_client=get_embedding_client_manager().client,
            value_es_repository=ValueESRepository(get_es_client_manager().client),
            metric_qdrant_repository=MetricQdrantRepository(
                get_qdrant_client_manager().client
            ),
            knowledge_graph_service=KnowledgeGraphService(
                KnowledgeGraphRepository(meta_session)
            ),
        )
        return await service.build(
            config_path,
            release_version=release_version,
            activate_aliases=False,
        )


async def publish(
    release_version: str,
    db_migration_version: str,
    config_path: Path | None = None,
) -> None:
    root = Path(__file__).parents[2]
    meta_mysql_client_manager.init()
    if config_path is not None:
        dw_mysql_client_manager.init()
        get_embedding_client_manager().init()
    get_qdrant_client_manager().init()
    get_es_client_manager().init()
    get_cube_client_manager().init()

    try:
        cube_repository = CubeRepository(
            get_cube_client_manager().client,
            app_config.cube,
        )
        cube_metadata = await cube_repository.get_metadata()
        cube_model_hash = hashlib.sha256(
            json.dumps(
                cube_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        compiler_id = cube_metadata.get("compilerId")
        if not isinstance(compiler_id, str) or not compiler_id:
            compiler_id = f"metadata-sha256:{cube_model_hash[:16]}"

        staged_result = None
        if config_path is not None:
            async with metadata_build_lock(
                meta_mysql_client_manager.engine, release_version
            ):
                staged_result = await _build_staging(config_path, release_version)

        qdrant = get_qdrant_client_manager().client
        cube_qdrant = CubeMemberQdrantRepository(qdrant)
        cube_collection = await cube_qdrant.get_alias_target()
        if cube_collection is None:
            raise ValueError("Cube Qdrant alias is not active")
        if not await qdrant.collection_exists(cube_collection):
            raise ValueError(f"Cube Qdrant collection is missing: {cube_collection}")
        column_repository = ColumnQdrantRepository(qdrant)
        column_collection = (
            staged_result.column_collection
            if staged_result is not None
            else await column_repository.get_alias_target()
        )
        if column_collection is None:
            raise ValueError("Column Qdrant target is not active")
        metric_repository = MetricQdrantRepository(qdrant)
        metric_collection = (
            staged_result.metric_collection
            if staged_result is not None
            else await metric_repository.get_alias_target()
        )
        if metric_collection is None:
            raise ValueError("Metric Qdrant alias is not active")
        for collection in (column_collection, metric_collection):
            if not await qdrant.collection_exists(collection):
                raise ValueError(f"Qdrant collection is missing: {collection}")

        es_repository = ValueESRepository(get_es_client_manager().client)
        value_index = (
            staged_result.value_index
            if staged_result is not None
            else await es_repository.get_alias_target()
        )
        if value_index is None:
            raise ValueError("Value ES target is not active")
        if not await es_repository.client.indices.exists(index=value_index):
            raise ValueError(f"ES index is missing: {value_index}")

        async with meta_mysql_client_manager.session_factory() as session:
            repository = MetadataReleaseRepository(session)
            existing = await repository.get(release_version)
            released_at = (
                existing["manifest"].released_at
                if existing is not None
                else datetime.now(timezone.utc).isoformat()
            )
            manifest = MetadataReleaseManifest(
                release_version=release_version,
                app_version=_app_version(root),
                db_migration_version=db_migration_version,
                cube_model_hash=cube_model_hash,
                cube_compiler_id=compiler_id,
                field_metadata_version=_sha256_bytes(
                    root / "conf" / "meta_config.yaml"
                ),
                qdrant_column_collection=column_collection,
                qdrant_metric_collection=metric_collection,
                qdrant_cube_collection=cube_collection,
                es_value_index=value_index,
                embedding_model=app_config.embedding.model,
                embedding_dimension=app_config.qdrant.embedding_size,
                prompt_version=_prompt_version(root),
                released_at=released_at,
            )
            service = MetadataReleaseService(repository)
            if staged_result is None:
                record = await service.publish(manifest, validator=lambda: None)
            else:
                bindings = []
                if staged_result.column_collection is not None:
                    bindings.append(
                        MetadataAliasBinding(
                            "column",
                            column_repository,
                            staged_result.column_collection,
                            staged_result.previous_column_collection,
                        )
                    )
                if staged_result.value_index is not None:
                    bindings.append(
                        MetadataAliasBinding(
                            "value",
                            es_repository,
                            staged_result.value_index,
                            staged_result.previous_value_index,
                        )
                    )
                if staged_result.metric_collection is not None:
                    bindings.append(
                        MetadataAliasBinding(
                            "metric",
                            metric_repository,
                            staged_result.metric_collection,
                            staged_result.previous_metric_collection,
                        )
                    )
                coordinator = MetadataReleaseCoordinator(service)
                async with metadata_build_lock(
                    meta_mysql_client_manager.engine, release_version
                ):
                    record = await coordinator.publish(
                        manifest,
                        bindings,
                        validator=lambda: None,
                    )
            logger.info(
                "metadata release activated version={} manifest_sha256={}",
                record["manifest"].release_version,
                record["manifest_sha256"],
            )
    finally:
        await meta_mysql_client_manager.close()
        if config_path is not None:
            await dw_mysql_client_manager.close()
            await _close_embedding_client()
        await get_qdrant_client_manager().close()
        await get_es_client_manager().close()
        await get_cube_client_manager().close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--db-migration-version", required=True)
    parser.add_argument(
        "--conf",
        type=Path,
        help="提供元数据配置时，在同一进程 staging、切换 alias 并激活 manifest",
    )
    args = parser.parse_args()
    asyncio.run(publish(args.version, args.db_migration_version, args.conf))
