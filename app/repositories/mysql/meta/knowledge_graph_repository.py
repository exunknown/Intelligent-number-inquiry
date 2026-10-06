"""元数据库知识图谱仓储。"""

from collections import deque
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.knowledge_graph import (
    EDGE_TYPES,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    KnowledgeGraphPath,
)
from app.models.knowledge_graph import KnowledgeGraphEdgeMySQL, KnowledgeGraphNodeMySQL


class KnowledgeGraphRepository:
    """负责按元数据版本读写知识图谱。"""

    def __init__(self, session: AsyncSession, release_version: str | None = None):
        self.session = session
        self.release_version = release_version or "legacy"

    def set_release_version(self, release_version: str | None) -> None:
        """切换当前仓储默认读取版本。"""

        self.release_version = release_version or "legacy"

    async def clear_release(self, release_version: str | None = None) -> None:
        """清理指定版本的边和节点，保证同版本重建是完整替换。"""

        version = release_version or self.release_version
        await self.session.execute(
            delete(KnowledgeGraphEdgeMySQL).where(
                KnowledgeGraphEdgeMySQL.release_version == version
            )
        )
        await self.session.execute(
            delete(KnowledgeGraphNodeMySQL).where(
                KnowledgeGraphNodeMySQL.release_version == version
            )
        )

    async def replace_release(
        self,
        release_version: str,
        nodes: list[KnowledgeGraphNode],
        edges: list[KnowledgeGraphEdge],
    ) -> None:
        """校验并替换一个发布版本的全部图谱行。"""

        self._validate_release_rows(release_version, nodes, edges)
        await self.clear_release(release_version)
        self.session.add_all([self._node_model(node) for node in nodes])
        self.session.add_all([self._edge_model(edge) for edge in edges])

    async def has_release(self, release_version: str | None = None) -> bool:
        """判断指定版本是否至少存在一个图谱节点。"""

        version = release_version or self.release_version
        result = await self.session.execute(
            select(KnowledgeGraphNodeMySQL.node_id)
            .where(KnowledgeGraphNodeMySQL.release_version == version)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def count_release(self, release_version: str) -> tuple[int, int]:
        """返回指定版本的节点和边数量。"""

        node_result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgeGraphNodeMySQL)
            .where(KnowledgeGraphNodeMySQL.release_version == release_version)
        )
        edge_result = await self.session.execute(
            select(func.count())
            .select_from(KnowledgeGraphEdgeMySQL)
            .where(KnowledgeGraphEdgeMySQL.release_version == release_version)
        )
        return int(node_result.scalar_one()), int(edge_result.scalar_one())

    async def list_release_versions(self) -> list[str]:
        """返回实际已物化的图谱版本，最新写入版本排在前面。"""

        result = await self.session.execute(
            select(
                KnowledgeGraphNodeMySQL.release_version,
                func.max(KnowledgeGraphNodeMySQL.created_at).label("latest_created_at"),
            )
            .group_by(KnowledgeGraphNodeMySQL.release_version)
            .order_by(
                func.max(KnowledgeGraphNodeMySQL.created_at).desc(),
                KnowledgeGraphNodeMySQL.release_version.desc(),
            )
        )
        return [row[0] for row in result.all()]

    async def search_nodes(
        self,
        release_version: str,
        *,
        query: str = "",
        node_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[KnowledgeGraphNode], int]:
        """按标题或节点编号搜索指定版本的节点。"""

        conditions = [KnowledgeGraphNodeMySQL.release_version == release_version]
        normalized_query = query.strip()
        if normalized_query:
            pattern = f"%{normalized_query}%"
            conditions.append(
                or_(
                    KnowledgeGraphNodeMySQL.title.like(pattern),
                    KnowledgeGraphNodeMySQL.node_id.like(pattern),
                )
            )
        if node_type:
            conditions.append(KnowledgeGraphNodeMySQL.node_type == node_type)

        count_result = await self.session.execute(
            select(func.count()).select_from(KnowledgeGraphNodeMySQL).where(*conditions)
        )
        result = await self.session.execute(
            select(KnowledgeGraphNodeMySQL)
            .where(*conditions)
            .order_by(
                KnowledgeGraphNodeMySQL.node_type,
                KnowledgeGraphNodeMySQL.title,
                KnowledgeGraphNodeMySQL.node_id,
            )
            .offset(offset)
            .limit(limit)
        )
        return [self._node_entity(model) for model in result.scalars().all()], int(
            count_result.scalar_one()
        )

    async def list_release(
        self, release_version: str
    ) -> tuple[list[KnowledgeGraphNode], list[KnowledgeGraphEdge]]:
        """读取指定发布版本的完整图谱，供只读同步任务使用。"""

        node_result = await self.session.execute(
            select(KnowledgeGraphNodeMySQL)
            .where(KnowledgeGraphNodeMySQL.release_version == release_version)
            .order_by(KnowledgeGraphNodeMySQL.node_id)
        )
        edge_result = await self.session.execute(
            select(KnowledgeGraphEdgeMySQL)
            .where(KnowledgeGraphEdgeMySQL.release_version == release_version)
            .order_by(KnowledgeGraphEdgeMySQL.edge_id)
        )
        return (
            [self._node_entity(model) for model in node_result.scalars().all()],
            [self._edge_entity(model) for model in edge_result.scalars().all()],
        )

    async def expand_paths(
        self,
        release_version: str,
        seed_node_ids: list[str],
        allowed_edge_types: set[str],
        max_hops: int,
        max_nodes: int,
        max_paths: int,
    ) -> tuple[
        list[KnowledgeGraphNode],
        list[KnowledgeGraphEdge],
        list[KnowledgeGraphPath],
    ]:
        """按边白名单对指定版本做有界 BFS 路径扩展。"""

        self._validate_limits(max_hops, max_nodes, max_paths)
        unknown_edge_types = allowed_edge_types - EDGE_TYPES
        if unknown_edge_types:
            raise ValueError(
                "unsupported edge types: " + ", ".join(sorted(unknown_edge_types))
            )

        node_result = await self.session.execute(
            select(KnowledgeGraphNodeMySQL).where(
                KnowledgeGraphNodeMySQL.release_version == release_version
            )
        )
        edge_statement = select(KnowledgeGraphEdgeMySQL).where(
            KnowledgeGraphEdgeMySQL.release_version == release_version,
            KnowledgeGraphEdgeMySQL.edge_type.in_(sorted(allowed_edge_types)),
        )
        edge_result = await self.session.execute(edge_statement)

        node_models = node_result.scalars().all()
        edge_models = edge_result.scalars().all()
        node_map = {model.node_id: self._node_entity(model) for model in node_models}
        edge_entities = [self._edge_entity(model) for model in edge_models]
        adjacency: dict[str, list[KnowledgeGraphEdge]] = {}
        for edge in edge_entities:
            if (
                edge.source_node_id not in node_map
                or edge.target_node_id not in node_map
            ):
                continue
            adjacency.setdefault(edge.source_node_id, []).append(edge)
        for edges in adjacency.values():
            edges.sort(key=lambda item: (-item.weight, item.edge_id))

        queue = deque(
            (node_id, (node_id,), (), 1.0, 0)
            for node_id in dict.fromkeys(seed_node_ids)
            if node_id in node_map
        )
        selected_node_ids: list[str] = []
        selected_node_set: set[str] = set()
        for node_id, _, _, _, _ in queue:
            if len(selected_node_ids) >= max_nodes:
                break
            selected_node_ids.append(node_id)
            selected_node_set.add(node_id)

        paths: list[KnowledgeGraphPath] = []
        selected_edge_ids: list[str] = []
        selected_edge_set: set[str] = set()
        while queue and len(paths) < max_paths:
            current_id, path_node_ids, path_edge_ids, score, hops = queue.popleft()
            if hops >= max_hops:
                continue
            for edge in adjacency.get(current_id, ()):
                if edge.target_node_id in path_node_ids:
                    continue
                next_node_ids = path_node_ids + (edge.target_node_id,)
                next_edge_ids = path_edge_ids + (edge.edge_id,)
                if (
                    edge.target_node_id not in selected_node_set
                    and len(selected_node_ids) >= max_nodes
                ):
                    continue
                selected_node_ids.append(edge.target_node_id)
                selected_node_set.add(edge.target_node_id)
                selected_edge_ids.append(edge.edge_id)
                selected_edge_set.add(edge.edge_id)
                next_score = score * edge.weight
                paths.append(
                    KnowledgeGraphPath(
                        node_ids=next_node_ids,
                        edge_ids=next_edge_ids,
                        score=next_score,
                    )
                )
                queue.append(
                    (
                        edge.target_node_id,
                        next_node_ids,
                        next_edge_ids,
                        next_score,
                        hops + 1,
                    )
                )
                if len(paths) >= max_paths:
                    break

        nodes = [node_map[node_id] for node_id in selected_node_ids]
        edges = [edge for edge in edge_entities if edge.edge_id in selected_edge_set]
        edges.sort(key=lambda item: item.edge_id)
        paths.sort(key=lambda item: (-item.score, item.node_ids))
        return nodes, edges, paths

    @staticmethod
    def _validate_limits(max_hops: int, max_nodes: int, max_paths: int) -> None:
        if not 1 <= max_hops <= 2:
            raise ValueError("max_hops must be between 1 and 2")
        if max_nodes < 1:
            raise ValueError("max_nodes must be positive")
        if max_paths < 1:
            raise ValueError("max_paths must be positive")

    @staticmethod
    def _validate_release_rows(
        release_version: str,
        nodes: list[KnowledgeGraphNode],
        edges: list[KnowledgeGraphEdge],
    ) -> None:
        if not release_version.strip():
            raise ValueError("release_version must not be empty")
        node_ids: set[str] = set()
        for node in nodes:
            if node.release_version != release_version:
                raise ValueError(
                    "node release_version does not match requested version"
                )
            if node.node_id in node_ids:
                raise ValueError(f"duplicate node: {node.node_id}")
            node_ids.add(node.node_id)

        edge_ids: set[str] = set()
        for edge in edges:
            if edge.release_version != release_version:
                raise ValueError(
                    "edge release_version does not match requested version"
                )
            if edge.edge_id in edge_ids:
                raise ValueError(f"duplicate edge: {edge.edge_id}")
            if (
                edge.source_node_id not in node_ids
                or edge.target_node_id not in node_ids
            ):
                raise ValueError(f"dangling edge: {edge.edge_id}")
            edge_ids.add(edge.edge_id)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def _node_model(cls, node: KnowledgeGraphNode) -> KnowledgeGraphNodeMySQL:
        payload = node.to_dict()
        return KnowledgeGraphNodeMySQL(
            release_version=node.release_version,
            node_id=node.node_id,
            node_type=node.node_type,
            title=node.title,
            description=node.description,
            payload_json=payload["payload"],
            source=node.source,
            confidence=node.confidence,
            created_at=cls._now(),
        )

    @classmethod
    def _edge_model(cls, edge: KnowledgeGraphEdge) -> KnowledgeGraphEdgeMySQL:
        payload = edge.to_dict()
        return KnowledgeGraphEdgeMySQL(
            release_version=edge.release_version,
            edge_id=edge.edge_id,
            source_node_id=edge.source_node_id,
            target_node_id=edge.target_node_id,
            edge_type=edge.edge_type,
            weight=edge.weight,
            evidence_json=payload["evidence"],
            source=edge.source,
            created_at=cls._now(),
        )

    @staticmethod
    def _node_entity(model: KnowledgeGraphNodeMySQL) -> KnowledgeGraphNode:
        return KnowledgeGraphNode(
            node_id=model.node_id,
            node_type=model.node_type,
            title=model.title,
            description=model.description,
            payload=dict(model.payload_json or {}),
            source=model.source,
            confidence=model.confidence,
            release_version=model.release_version,
        )

    @staticmethod
    def _edge_entity(model: KnowledgeGraphEdgeMySQL) -> KnowledgeGraphEdge:
        return KnowledgeGraphEdge(
            edge_id=model.edge_id,
            source_node_id=model.source_node_id,
            target_node_id=model.target_node_id,
            edge_type=model.edge_type,
            weight=model.weight,
            evidence=dict(model.evidence_json or {}),
            source=model.source,
            release_version=model.release_version,
        )
