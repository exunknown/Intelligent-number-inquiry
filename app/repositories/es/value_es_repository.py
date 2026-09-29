"""
字段取值 ES 仓储

把字段真实取值组织成 Elasticsearch 全文索引，并提供索引创建 批量写入和关键词检索能力

Service 层负责决定哪些字段需要同步
Repository 只关心索引是否存在 ValueInfo 如何写进 ES 以及如何按关键词召回
"""

import hashlib
from dataclasses import asdict

from elasticsearch import AsyncElasticsearch

from app.entities.value_info import ValueInfo


class ValueESRepository:
    """负责字段取值全文索引的创建 写入和基础检索"""

    index_name = "value_index"
    alias_name = "value_index_active"
    # value 字段使用 IK 分词，中文值才能按全文方式检索
    index_mappings = {
        "dynamic": False,
        "properties": {
            "id": {"type": "keyword"},
            "value": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_max_word",
            },
            "column_id": {"type": "keyword"},
        },
    }

    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    async def get_alias_target(self) -> str | None:
        """读取字段值索引 alias 当前指向的物理索引。"""
        if not await self.client.indices.exists(index=self.alias_name):
            return None
        response = await self.client.indices.get_alias(name=self.alias_name)
        targets = list(response)
        if len(targets) > 1:
            raise ValueError("value index alias must target exactly one index")
        return targets[0] if targets else None

    async def ensure_alias(self) -> str:
        """为旧固定索引补建稳定 alias。"""
        target = await self.get_alias_target()
        if target is not None:
            return target
        await self.ensure_index()
        await self.client.indices.put_alias(index=self.index_name, name=self.alias_name)
        return self.index_name

    async def create_physical_index(self, release_version: str) -> str:
        """创建本次发布专用的 staging 索引。"""
        safe_version = "".join(
            char if char.isalnum() or char in "_-" else "_" for char in release_version
        )[:40]
        suffix = hashlib.sha256(release_version.encode("utf-8")).hexdigest()[:8]
        index_name = f"value_index_{safe_version}_{suffix}"
        if await self.client.indices.exists(index=index_name):
            return index_name
        await self.ensure_index(index_name=index_name)
        return index_name

    async def count_documents(self, index_name: str) -> int:
        response = await self.client.count(index=index_name)
        return int(response["count"])

    async def swap_alias(self, index_name: str, previous_index: str | None) -> None:
        actions = []
        if previous_index is not None:
            actions.append(
                {"remove": {"index": previous_index, "alias": self.alias_name}}
            )
        actions.append({"add": {"index": index_name, "alias": self.alias_name}})
        await self.client.indices.update_aliases(actions=actions)

    async def delete_index(self, index_name: str) -> None:
        if not index_name.startswith("value_index_") or index_name in {
            self.index_name,
            self.alias_name,
        }:
            raise ValueError("only generated value indexes can be deleted")
        await self.client.indices.delete(index=index_name)

    async def ensure_index(self, index_name: str | None = None):
        """确保字段取值索引已经创建好"""
        index_name = index_name or self.index_name
        if not await self.client.indices.exists(index=index_name):
            await self.client.indices.create(
                index=index_name, mappings=self.index_mappings
            )

    async def index(
        self,
        value_infos: list[ValueInfo],
        batch_size=20,
        index_name: str | None = None,
    ):
        """分批写入字段取值，避免一次 bulk 过大"""
        if not value_infos:
            return

        index_name = index_name or self.index_name
        for i in range(0, len(value_infos), batch_size):
            batch_value_infos = value_infos[i : i + batch_size]
            batch_operations = []
            for value_info in batch_value_infos:
                # 用 ValueInfo.id 作为文档 id，这样重复构建时会覆盖同一条值记录
                batch_operations.append(
                    {"index": {"_index": index_name, "_id": value_info.id}}
                )
                batch_operations.append(asdict(value_info))
            await self.client.bulk(operations=batch_operations)
        await self.client.indices.refresh(index=index_name)

    async def search(
        self, keyword: str, score_threshold: float = 0.6, limit: int = 20
    ) -> list[ValueInfo]:
        """按关键词全文检索字段取值，并还原为 ValueInfo 实体"""

        index = (
            self.alias_name
            if await self.get_alias_target() is not None
            else self.index_name
        )
        resp = await self.client.search(
            index=index,
            # value 字段启用了 IK 分词，match 查询可以处理中文短语和枚举值匹配
            query={"match": {"value": keyword}},
            size=limit,
            # 过滤掉相关度过低的命中，避免把明显无关的取值带入后续上下文
            min_score=score_threshold,
        )
        # ES 文档 _source 中保存的是 ValueInfo 的字段结构，业务层继续使用实体对象
        return [ValueInfo(**hit["_source"]) for hit in resp["hits"]["hits"]]
