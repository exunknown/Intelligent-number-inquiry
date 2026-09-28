"""Cube 受治理成员的 alias 感知 Qdrant 仓储。"""

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    VectorParams,
)

from app.conf.app_config import app_config
from app.core.log import logger
from app.entities.cube_member import (
    CubeMember,
    CubeMemberEmbeddingEntry,
    CubeMemberType,
)


class CubeMemberQdrantRepository:
    """管理 Cube 成员物理集合及稳定查询 alias。"""

    alias_name = "cube_member_collection"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def create_physical_collection(self) -> str:
        """创建带 UTC 时间戳和随机后缀的物理集合。"""

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        collection_name = f"cube_member_{timestamp}_{uuid.uuid4().hex[:8]}"
        try:
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=app_config.qdrant.embedding_size,
                    distance=Distance.COSINE,
                ),
            )
        except Exception:
            # 创建请求的响应可能丢失；按本地已生成的唯一名称尽力清理。
            try:
                await self.client.delete_collection(collection_name=collection_name)
            except Exception:
                logger.warning(
                    "Cube staging collection 创建结果无法确认且清理失败 collection={}",
                    collection_name,
                )
            raise
        return collection_name

    async def upsert_entries(
        self,
        collection_name: str,
        entries: list[CubeMemberEmbeddingEntry],
        embeddings: list[list[float]],
        batch_size: int = 8,
    ) -> None:
        """把向量和成员 payload 严格按位置配对后分批写入。"""

        if len(entries) != len(embeddings):
            raise ValueError("entries and embeddings length must be equal")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        points = [
            PointStruct(
                id=entry.id,
                vector=embedding,
                payload=asdict(entry.member),
            )
            for entry, embedding in zip(entries, embeddings, strict=True)
        ]
        for index in range(0, len(points), batch_size):
            await self.client.upsert(
                collection_name=collection_name,
                points=points[index : index + batch_size],
            )

    async def count_points(self, collection_name: str) -> int:
        """精确统计物理集合中的 point 数量。"""

        result = await self.client.count(
            collection_name=collection_name,
            exact=True,
        )
        return result.count

    async def get_alias_target(self) -> str | None:
        """读取稳定 alias 当前指向的物理集合。"""

        response = await self.client.get_aliases()
        for alias in response.aliases:
            if alias.alias_name == self.alias_name:
                return alias.collection_name
        return None

    async def swap_alias(
        self, collection_name: str, previous_collection: str | None
    ) -> None:
        """在一次 Qdrant 请求中原子切换稳定 alias。"""

        operations = []
        if previous_collection is not None:
            operations.append(
                DeleteAliasOperation(
                    delete_alias=DeleteAlias(alias_name=self.alias_name)
                )
            )
        operations.append(
            CreateAliasOperation(
                create_alias=CreateAlias(
                    collection_name=collection_name,
                    alias_name=self.alias_name,
                )
            )
        )
        await self.client.update_collection_aliases(
            change_aliases_operations=operations
        )

    async def delete_collection(self, collection_name: str) -> None:
        """只允许删除本仓储创建的物理集合。"""

        if (
            not collection_name.startswith("cube_member_")
            or collection_name == self.alias_name
        ):
            raise ValueError(
                "only generated cube_member physical collections can be deleted"
            )
        await self.client.delete_collection(collection_name=collection_name)

    async def search(
        self,
        embedding: list[float],
        member_types: set[CubeMemberType],
        score_threshold: float = 0.6,
        limit: int = 10,
    ) -> list[CubeMember]:
        """通过稳定 alias 检索指定成员类型并按成员名去重。"""

        if not member_types:
            return []
        result = await self.client.query_points(
            collection_name=self.alias_name,
            query=embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="member_type",
                        match=MatchAny(any=sorted(member_types)),
                    )
                ]
            ),
            score_threshold=score_threshold,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return self._deduplicate_members(point.payload for point in result.points)

    async def list_members(self) -> list[CubeMember]:
        """滚动读取稳定 alias 后的全部成员。"""

        payloads = []
        offset = None
        while True:
            points, offset = await self.client.scroll(
                collection_name=self.alias_name,
                offset=offset,
                limit=256,
                with_payload=True,
                with_vectors=False,
            )
            payloads.extend(point.payload for point in points)
            if offset is None:
                break
        return self._deduplicate_members(payloads)

    @staticmethod
    def _deduplicate_members(payloads: object) -> list[CubeMember]:
        members: list[CubeMember] = []
        seen_names: set[str] = set()
        for payload in payloads:
            if not isinstance(payload, dict):
                raise ValueError("Cube member Qdrant payload must be an object")
            member = CubeMember(**payload)
            if member.name not in seen_names:
                seen_names.add(member.name)
                members.append(member)
        return members
