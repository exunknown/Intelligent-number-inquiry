"""Cube 受治理成员向 Qdrant 同步的应用服务。"""

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.core.log import logger
from app.entities.cube_member import (
    CubeMemberEmbeddingEntry,
    CubeMetadataSyncResult,
    extract_cube_members,
    iter_member_embedding_entries,
)
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)


class CubeMetadataService:
    """编排 Cube 元数据提取、向量化和原子 alias 切换。"""

    def __init__(
        self,
        cube_repository: CubeRepository,
        cube_member_qdrant_repository: CubeMemberQdrantRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        semantic_view: str,
    ):
        self.cube_repository = cube_repository
        self.cube_member_qdrant_repository = cube_member_qdrant_repository
        self.embedding_client = embedding_client
        self.semantic_view = semantic_view

    async def sync(self) -> CubeMetadataSyncResult:
        """完整构建新集合，校验计数后再原子切换稳定 alias。"""

        metadata = await self.cube_repository.get_metadata()
        members, compiler_id = extract_cube_members(metadata, self.semantic_view)
        entries: list[CubeMemberEmbeddingEntry] = []
        for member in members:
            entries.extend(iter_member_embedding_entries(member))
        if not members or not entries:
            raise ValueError("Cube semantic view contains no governed members")

        collection_name: str | None = None
        alias_swapped = False
        preserve_staging = False
        try:
            # 先创建 staging，确保后续任何失败都有明确的清理对象。
            collection_name = (
                await self.cube_member_qdrant_repository.create_physical_collection()
            )
            embeddings: list[list[float]] = []
            for index in range(0, len(entries), 8):
                batch_entries = entries[index : index + 8]
                batch_embeddings = await self.embedding_client.aembed_documents(
                    [entry.embedding_text for entry in batch_entries]
                )
                if len(batch_embeddings) != len(batch_entries):
                    raise ValueError(
                        "Embedding response length does not match request length"
                    )
                embeddings.extend(batch_embeddings)

            await self.cube_member_qdrant_repository.upsert_entries(
                collection_name,
                entries,
                embeddings,
            )
            point_count = await self.cube_member_qdrant_repository.count_points(
                collection_name
            )
            if point_count != len(entries):
                raise RuntimeError(
                    "Qdrant point count validation failed: "
                    f"expected {len(entries)}, got {point_count}"
                )

            previous_collection = (
                await self.cube_member_qdrant_repository.get_alias_target()
            )
            try:
                await self.cube_member_qdrant_repository.swap_alias(
                    collection_name,
                    previous_collection,
                )
                alias_swapped = True
            except Exception:
                try:
                    current_collection = (
                        await self.cube_member_qdrant_repository.get_alias_target()
                    )
                except Exception:
                    # 无法确认提交结果时保留 staging，避免误删 alias 已指向的新集合。
                    preserve_staging = True
                    logger.warning(
                        "Cube alias 切换结果无法确认，保留 staging collection={}",
                        collection_name,
                    )
                    raise
                if current_collection != collection_name:
                    raise
                alias_swapped = True
                logger.warning(
                    "Cube alias 切换响应异常，但已确认新 alias 生效 collection={}",
                    collection_name,
                )
        except Exception:
            if (
                collection_name is not None
                and not alias_swapped
                and not preserve_staging
            ):
                try:
                    await self.cube_member_qdrant_repository.delete_collection(
                        collection_name
                    )
                except Exception:
                    logger.warning(
                        "Cube 元数据同步失败，且 staging collection 清理失败 collection={}",
                        collection_name,
                    )
            raise

        if previous_collection is not None and previous_collection != collection_name:
            try:
                await self.cube_member_qdrant_repository.delete_collection(
                    previous_collection
                )
            except Exception:
                logger.warning(
                    "Cube alias 已切换，但旧 collection 清理失败 collection={}",
                    previous_collection,
                )

        return CubeMetadataSyncResult(
            compiler_id=compiler_id,
            member_count=len(members),
            point_count=point_count,
            collection_name=collection_name,
        )
