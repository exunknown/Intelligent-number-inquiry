"""
指标向量仓储

管理指标向量集合，并把 Service 层准备好的指标 point 批量写入 Qdrant

字段和指标虽然都用向量检索，但它们是两类不同对象
所以指标单独使用 metric_info_collection，避免后续召回时和字段结果混在一起
"""

import hashlib
import re

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
)
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.conf.app_config import app_config
from app.entities.metric_info import MetricInfo


class MetricQdrantRepository:
    """负责指标向量集合的创建 写入和基础检索"""

    collection_name = "metric_info_collection"
    alias_name = "metric_info_active"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def get_alias_target(self) -> str | None:
        response = await self.client.get_aliases()
        for alias in response.aliases:
            if alias.alias_name == self.alias_name:
                return alias.collection_name
        return None

    async def ensure_alias(self) -> str:
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
        slug = re.sub(r"[^A-Za-z0-9_-]", "_", release_version)[:40]
        suffix = hashlib.sha256(release_version.encode("utf-8")).hexdigest()[:8]
        collection_name = f"metric_info_{slug}_{suffix}"
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
        if not collection_name.startswith("metric_info_") or collection_name in {
            self.collection_name,
            self.alias_name,
        }:
            raise ValueError("only generated metric_info collections can be deleted")
        await self.client.delete_collection(collection_name=collection_name)

    async def ensure_collection(self, collection_name: str | None = None):
        """确保指标向量集合存在，并按当前 Embedding 维度初始化"""
        collection_name = collection_name or self.collection_name
        if not await self.client.collection_exists(collection_name):
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    # 向量维度必须和 Embedding 模型输出一致，否则写入时会失败
                    size=app_config.qdrant.embedding_size,
                    distance=Distance.COSINE,
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
        """分批 upsert 指标向量点，避免一次提交过多 point"""
        # ids embeddings payloads 三个列表按相同下标组成一条完整的 Qdrant point
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
    ) -> list[MetricInfo]:
        """按向量相似度检索指标元数据，并还原为 MetricInfo 实体"""

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
        # Qdrant point 的 payload 中保存的是指标元数据，业务层继续使用 MetricInfo
        return [MetricInfo(**point.payload) for point in result.points]
