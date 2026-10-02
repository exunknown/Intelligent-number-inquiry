"""语义模型发布对外部存储的具体适配。"""

from dataclasses import dataclass
from datetime import datetime, timezone

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.core.log import logger
from app.entities.cube_member import (
    CubeMember,
    CubeMemberEmbeddingEntry,
    iter_member_embedding_entries,
)
from app.entities.metadata_release import MetadataReleaseManifest
from app.entities.semantic_model import SemanticMember, SemanticModelSnapshot
from app.services.cube_semantic_model_compiler import (
    CubeCompilationResult,
    CubeSemanticModelCompiler,
)


@dataclass(frozen=True)
class SemanticSearchStagingResult:
    """候选语义模型在 Qdrant 中的 staging 结果。"""

    collection_name: str
    previous_collection: str | None
    member_count: int
    point_count: int


class SemanticModelReleaseAdapter:
    """连接候选编译、Qdrant staging 和语义快照事务。"""

    def __init__(
        self,
        *,
        semantic_repository,
        metadata_release_repository,
        qdrant_repository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        compiler: CubeSemanticModelCompiler | None = None,
    ):
        self.semantic_repository = semantic_repository
        self.metadata_release_repository = metadata_release_repository
        self.qdrant_repository = qdrant_repository
        self.embedding_client = embedding_client
        self.compiler = compiler or CubeSemanticModelCompiler()
        self.compilation: CubeCompilationResult | None = None
        self.staging: SemanticSearchStagingResult | None = None

    async def compile_model(
        self, snapshot: SemanticModelSnapshot
    ) -> CubeCompilationResult:
        result = await self.compiler.compile(snapshot)
        self.compilation = result
        return result

    async def stage_search_index(
        self, snapshot: SemanticModelSnapshot
    ) -> SemanticSearchStagingResult:
        if (
            self.compilation is None
            or self.compilation.release_version != snapshot.release_version
        ):
            await self.compile_model(snapshot)

        members = [_cube_member(member) for member in snapshot.members]
        entries: list[CubeMemberEmbeddingEntry] = []
        for member in members:
            entries.extend(iter_member_embedding_entries(member))
        if not members or not entries:
            raise ValueError("Cube semantic model contains no governed members")

        collection_name: str | None = None
        try:
            collection_name = await self.qdrant_repository.create_physical_collection()
            embeddings: list[list[float]] = []
            for index in range(0, len(entries), 8):
                batch = entries[index : index + 8]
                batch_embeddings = await self.embedding_client.aembed_documents(
                    [entry.embedding_text for entry in batch]
                )
                if len(batch_embeddings) != len(batch):
                    raise ValueError(
                        "Embedding response length does not match request length"
                    )
                embeddings.extend(batch_embeddings)

            await self.qdrant_repository.upsert_entries(
                collection_name, entries, embeddings
            )
            point_count = await self.qdrant_repository.count_points(collection_name)
            if point_count != len(entries):
                raise RuntimeError(
                    "Qdrant point count validation failed: "
                    f"expected {len(entries)}, got {point_count}"
                )
            previous_collection = await self.qdrant_repository.get_alias_target()
        except Exception:
            if collection_name is not None:
                try:
                    await self.qdrant_repository.delete_collection(collection_name)
                except Exception:
                    logger.warning(
                        "语义模型 Qdrant staging 清理失败 collection={}",
                        collection_name,
                    )
            raise

        self.staging = SemanticSearchStagingResult(
            collection_name=collection_name,
            previous_collection=previous_collection,
            member_count=len(members),
            point_count=point_count,
        )
        return self.staging

    async def persist_and_activate(
        self,
        snapshot: SemanticModelSnapshot,
        actor_id: str,
        reason: str,
    ) -> dict:
        """切换候选 alias，并在 Meta 事务中物化和激活版本。"""

        if self.compilation is None or self.staging is None:
            raise RuntimeError("semantic model must be compiled and staged first")
        if self.compilation.release_version != snapshot.release_version:
            raise RuntimeError(
                "compiled semantic model version does not match snapshot"
            )

        base_manifest = await self._active_manifest()
        manifest = MetadataReleaseManifest(
            release_version=snapshot.release_version,
            app_version=base_manifest.app_version,
            db_migration_version=base_manifest.db_migration_version,
            cube_model_hash=self.compilation.model_hash,
            cube_compiler_id=self.compilation.compiler_id,
            field_metadata_version=base_manifest.field_metadata_version,
            qdrant_column_collection=base_manifest.qdrant_column_collection,
            qdrant_metric_collection=base_manifest.qdrant_metric_collection,
            qdrant_cube_collection=self.staging.collection_name,
            es_value_index=base_manifest.es_value_index,
            embedding_model=base_manifest.embedding_model,
            embedding_dimension=base_manifest.embedding_dimension,
            prompt_version=base_manifest.prompt_version,
            released_at=datetime.now(timezone.utc).isoformat(),
        )

        alias_switched = False

        async def materialize() -> None:
            nonlocal alias_switched
            await self._switch_alias()
            alias_switched = True
            await self.semantic_repository.persist_release_snapshot(
                snapshot, actor_id=actor_id
            )

        try:
            result = await self.metadata_release_repository.activate_manifest_with_materializer(
                manifest, materialize
            )
        except Exception:
            if alias_switched:
                await self._restore_alias()
            raise

        await self._delete_previous_collection()
        return result

    async def activate_release(self, snapshot, actor_id: str, reason: str):
        """禁止绕过候选 staging 的旧式激活入口。"""

        raise RuntimeError("semantic model activation requires staged publication")

    async def rollback_release(
        self, release_version: str, actor_id: str, reason: str
    ) -> dict:
        """为目标版本重建检索 staging 后再激活，避免只切 MySQL。"""

        snapshot = await self.semantic_repository.get_snapshot(release_version)
        if snapshot is None:
            raise ValueError("semantic model release snapshot not found")
        await self.compile_model(snapshot)
        await self.stage_search_index(snapshot)

        record = await self.metadata_release_repository.get(release_version)
        if record is None or record["status"] not in {"validated", "active"}:
            raise ValueError("release version is not validated")

        alias_switched = False

        async def switch_only() -> None:
            nonlocal alias_switched
            await self._switch_alias()
            alias_switched = True

        try:
            result = await self.metadata_release_repository.activate_with_materializer(
                release_version, switch_only
            )
        except Exception:
            if alias_switched:
                await self._restore_alias()
            raise
        await self._delete_previous_collection()
        return result

    async def _active_manifest(self) -> MetadataReleaseManifest:
        version = await self.metadata_release_repository.get_active_version()
        if version is None:
            raise RuntimeError("active metadata release manifest is required")
        record = await self.metadata_release_repository.get(version)
        if record is None:
            raise RuntimeError("active metadata release manifest is missing")
        return record["manifest"]

    async def _switch_alias(self) -> None:
        assert self.staging is not None
        try:
            await self.qdrant_repository.swap_alias(
                self.staging.collection_name,
                self.staging.previous_collection,
            )
        except Exception:
            current = await self.qdrant_repository.get_alias_target()
            if current != self.staging.collection_name:
                raise
            logger.warning(
                "语义模型 Qdrant alias 切换响应异常，但已确认新集合生效 collection={}",
                self.staging.collection_name,
            )

    async def _restore_alias(self) -> None:
        assert self.staging is not None
        if self.staging.previous_collection is None:
            logger.warning("语义模型发布失败但没有旧 Qdrant alias 可恢复")
            return
        try:
            await self.qdrant_repository.swap_alias(
                self.staging.previous_collection,
                self.staging.collection_name,
            )
        except Exception:
            logger.error(
                "语义模型 Qdrant alias 补偿失败 collection={}",
                self.staging.previous_collection,
            )

    async def _delete_previous_collection(self) -> None:
        assert self.staging is not None
        previous = self.staging.previous_collection
        if previous is None or previous == self.staging.collection_name:
            return
        try:
            await self.qdrant_repository.delete_collection(previous)
        except Exception:
            logger.warning(
                "语义模型 alias 已切换，但旧 collection 清理失败 collection={}",
                previous,
            )


def _cube_member(member: SemanticMember) -> CubeMember:
    """把语义成员投影为问数检索使用的 Cube 成员。"""

    return CubeMember(
        name=member.qualified_name,
        cube_name=member.cube_name,
        member_type=member.member_type,
        data_type=member.data_type,
        title=member.title,
        description=member.description,
        aliases=list(member.aliases),
        ai_context=member.ai_context,
        source_column_id=member.source_column_id,
        filterable=member.filterable,
    )
