"""知识图谱管理页查询服务。"""

from dataclasses import dataclass
from typing import Literal

from app.entities.knowledge_graph import EDGE_TYPES, KnowledgeGraphNode
from app.repositories.mysql.meta.metadata_release_repository import (
    MetadataReleaseRepository,
)

KnowledgeGraphBackend = Literal["mysql", "neo4j"]


class KnowledgeGraphReleaseNotFoundError(ValueError):
    """请求的元数据发布版本不存在。"""


class KnowledgeGraphNodeNotFoundError(ValueError):
    """请求的图谱种子节点不存在。"""


@dataclass(frozen=True)
class KnowledgeGraphQueryService:
    """为 Agent 管理页提供版本、节点和有界子图查询。"""

    graph_repository: object
    metadata_release_repository: MetadataReleaseRepository
    backend: KnowledgeGraphBackend

    async def list_releases(self) -> tuple[list[dict], str | None]:
        graph_versions = await self.graph_repository.list_release_versions()
        metadata_records = {
            record["release_version"]: record
            for record in await self.metadata_release_repository.list_releases()
        }
        metadata_active_version = (
            await self.metadata_release_repository.get_active_version()
        )
        active_version = (
            metadata_active_version
            if metadata_active_version in graph_versions
            else (graph_versions[0] if graph_versions else None)
        )
        items = []
        for release_version in graph_versions:
            record = metadata_records.get(release_version, {})
            node_count, edge_count = await self.graph_repository.count_release(
                release_version
            )
            items.append(
                {
                    "release_version": release_version,
                    "status": record.get("status", "graph_only"),
                    "active": release_version == active_version,
                    "created_at": record.get("created_at"),
                    "node_count": node_count,
                    "edge_count": edge_count,
                }
            )
        return items, active_version

    async def search_nodes(
        self,
        release_version: str | None,
        query: str,
        node_type: str | None,
        limit: int,
        offset: int,
    ) -> tuple[str, list[KnowledgeGraphNode], int]:
        version = await self._resolve_release(release_version)
        nodes, total = await self.graph_repository.search_nodes(
            version,
            query=query,
            node_type=node_type,
            limit=limit,
            offset=offset,
        )
        return version, nodes, total

    async def expand_subgraph(
        self,
        release_version: str | None,
        seed_node_id: str,
        max_hops: int,
        max_nodes: int,
        max_paths: int,
    ):
        version = await self._resolve_release(release_version)
        nodes, edges, paths = await self.graph_repository.expand_paths(
            version,
            [seed_node_id],
            set(EDGE_TYPES),
            max_hops=max_hops,
            max_nodes=max_nodes,
            max_paths=max_paths,
        )
        if not any(node.node_id == seed_node_id for node in nodes):
            raise KnowledgeGraphNodeNotFoundError(seed_node_id)
        return version, nodes, edges, paths, len(nodes) >= max_nodes

    async def _resolve_release(self, release_version: str | None) -> str:
        if release_version:
            node_count, edge_count = await self.graph_repository.count_release(
                release_version
            )
            if node_count == 0 and edge_count == 0:
                raise KnowledgeGraphReleaseNotFoundError(release_version)
            return release_version

        active_version = await self.metadata_release_repository.get_active_version()
        if active_version:
            node_count, edge_count = await self.graph_repository.count_release(
                active_version
            )
            if node_count > 0 or edge_count > 0:
                return active_version
        graph_versions = await self.graph_repository.list_release_versions()
        if graph_versions:
            return graph_versions[0]
        raise KnowledgeGraphReleaseNotFoundError("graph release not found")

    @staticmethod
    def safe_node_metadata(node: KnowledgeGraphNode) -> dict[str, object]:
        """只保留图谱页面需要的有限业务元数据。"""

        allowed_keys = {
            "value",
            "column_id",
            "table_id",
            "role",
            "type",
            "alias",
        }
        return {
            key: value for key, value in node.payload.items() if key in allowed_keys
        }
