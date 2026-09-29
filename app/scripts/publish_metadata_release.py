"""校验并激活一次元数据 manifest。"""

import argparse
import asyncio
import hashlib
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from app.clients.cube_client_manager import get_cube_client_manager
from app.clients.es_client_manager import get_es_client_manager
from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.clients.qdrant_client_manager import get_qdrant_client_manager
from app.conf.app_config import app_config
from app.core.log import logger
from app.entities.metadata_release import MetadataReleaseManifest
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.meta.metadata_release_repository import (
    MetadataReleaseRepository,
)
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
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


async def publish(release_version: str, db_migration_version: str) -> None:
    root = Path(__file__).parents[2]
    meta_mysql_client_manager.init()
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

        qdrant = get_qdrant_client_manager().client
        cube_qdrant = CubeMemberQdrantRepository(qdrant)
        cube_collection = await cube_qdrant.get_alias_target()
        if cube_collection is None:
            raise ValueError("Cube Qdrant alias is not active")
        if not await qdrant.collection_exists(cube_collection):
            raise ValueError(f"Cube Qdrant collection is missing: {cube_collection}")
        column_repository = ColumnQdrantRepository(qdrant)
        column_collection = await column_repository.get_alias_target()
        if column_collection is None:
            raise ValueError("Column Qdrant alias is not active")
        metric_repository = MetricQdrantRepository(qdrant)
        metric_collection = await metric_repository.get_alias_target()
        if metric_collection is None:
            raise ValueError("Metric Qdrant alias is not active")
        for collection in (column_collection, metric_collection):
            if not await qdrant.collection_exists(collection):
                raise ValueError(f"Qdrant collection is missing: {collection}")

        es_repository = ValueESRepository(get_es_client_manager().client)
        value_index = await es_repository.get_alias_target()
        if value_index is None:
            raise ValueError("Value ES alias is not active")
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
            record = await service.publish(manifest, validator=lambda: None)
            logger.info(
                "metadata release activated version={} manifest_sha256={}",
                record["manifest"].release_version,
                record["manifest_sha256"],
            )
    finally:
        await meta_mysql_client_manager.close()
        await get_qdrant_client_manager().close()
        await get_es_client_manager().close()
        await get_cube_client_manager().close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--db-migration-version", required=True)
    args = parser.parse_args()
    asyncio.run(publish(args.version, args.db_migration_version))
