"""
字段向量仓储

管理字段向量集合并把已经准备好的 point 批量写入 Qdrant

Service 层负责决定一个字段要拆成哪些 point
Repository 只关心集合存在和向量点如何稳定落库
"""

import hashlib
import re

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    PointStruct,
)
from qdrant_client.models import Distance, VectorParams

from app.conf.app_config import app_config
from app.entities.column_info import ColumnInfo


class ColumnQdrantRepository:
    """负责字段向量集合的创建 写入和基础检索"""

    collection_name = "column_info_collection"
    alias_name = "column_info_active"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def get_alias_target(self) -> str | None:
        """读取稳定 alias 当前指向的字段物理集合。"""
        response = await self.client.get_aliases()
        for alias in response.aliases:
            if alias.alias_name == self.alias_name:
                return alias.collection_name
        return None

    async def ensure_alias(self) -> str:
        """为旧固定集合补建稳定 alias，返回当前活动物理集合。"""
        target = await self.get_alias_target()
        if target is not None:
            return target
        await self.ensure_collection()
        await self.client.update_collection_aliases(
            change_aliases_operations=[
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        collection_name=self.collection_name,
                        alias_name=self.alias_name,
                    )
                )
            ]
        )
        return self.collection_name

    async def create_physical_collection(self, release_version: str) -> str:
        """创建本次发布专用的 staging 集合。"""
        slug = re.sub(r"[^A-Za-z0-9_-]", "_", release_version)[:40]
        suffix = hashlib.sha256(release_version.encode("utf-8")).hexdigest()[:8]
        collection_name = f"column_info_{slug}_{suffix}"
        if await self.client.collection_exists(collection_name):
            return collection_name
        await self.ensure_collection(collection_name)
        return collection_name

    async def count_points(self, collection_name: str) -> int:
        result = await self.client.count(collection_name=collection_name, exact=True)
        return result.count

    async def swap_alias(
        self, collection_name: str, previous_collection: str | None
    ) -> None:
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
        if not collection_name.startswith("column_info_") or collection_name in {
            self.collection_name,
            self.alias_name,
        }:
            raise ValueError("only generated column_info collections can be deleted")
        await self.client.delete_collection(collection_name=collection_name)

    async def ensure_collection(self, collection_name: str | None = None):
        """确保字段向量集合存在，并按配置中的维度初始化"""
        collection_name = collection_name or self.collection_name
        if not await self.client.collection_exists(collection_name):
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=app_config.qdrant.embedding_size, distance=Distance.COSINE
                ),
            )

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        payloads: list[dict],
        batch_size: int = 10,
        collection_name: str | None = None,
    ):
        """分批 upsert 字段向量点，避免一次提交过多 point"""
        points: list[PointStruct] = [
            PointStruct(id=id, vector=embedding, payload=payload)
            for id, embedding, payload in zip(ids, embeddings, payloads)
        ]
        for i in range(0, len(points), batch_size):
            await self.client.upsert(
                collection_name=collection_name or self.collection_name,
                points=points[i : i + batch_size],
            )

    async def search(
        self, embedding: list[float], score_threshold: float = 0.6, limit: int = 20
    ) -> list[ColumnInfo]:
        """按向量相似度检索字段元数据，并还原为 ColumnInfo 实体"""
        collection_name = (
            self.alias_name
            if await self.get_alias_target() is not None
            else self.collection_name
        )
        result = await self.client.query_points(
            collection_name=collection_name,
            query=embedding,
            limit=limit,
            score_threshold=score_threshold,
        )
        # Qdrant 只保存字段元数据 payload，业务层继续使用 ColumnInfo
        return [ColumnInfo(**point.payload) for point in result.points]
