"""Neo4j 元数据知识图谱仓储。"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from neo4j import AsyncDriver, AsyncManagedTransaction

from app.entities.knowledge_graph import (
    BUSINESS_NODE_TYPES,
    EDGE_TYPES,
    TECHNICAL_NODE_TYPES,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    KnowledgeGraphPath,
)

_NODE_LABEL = "KnowledgeGraphNode"
_EDGE_TYPE = "KNOWLEDGE_GRAPH_EDGE"

_CLEAR_EDGES_QUERY = f"""
MATCH ()-[edge:{_EDGE_TYPE} {{release_version: $release_version}}]->()
DELETE edge
"""

_CLEAR_NODES_QUERY = f"""
MATCH (node:{_NODE_LABEL} {{release_version: $release_version}})
DETACH DELETE node
"""

_WRITE_NODES_QUERY = f"""
UNWIND $nodes AS row
MERGE (node:{_NODE_LABEL} {{
    release_version: row.release_version,
    node_id: row.node_id
}})
SET node.node_type = row.node_type,
    node.title = row.title,
    node.description = row.description,
    node.payload_json = row.payload_json,
    node.source = row.source,
    node.confidence = row.confidence
"""

_WRITE_EDGES_QUERY = f"""
UNWIND $edges AS row
MATCH (source:{_NODE_LABEL} {{
    release_version: row.release_version,
    node_id: row.source_node_id
}})
MATCH (target:{_NODE_LABEL} {{
    release_version: row.release_version,
    node_id: row.target_node_id
}})
MERGE (source)-[edge:{_EDGE_TYPE} {{
    release_version: row.release_version,
    edge_id: row.edge_id
}}]->(target)
SET edge.source_node_id = row.source_node_id,
    edge.target_node_id = row.target_node_id,
    edge.edge_type = row.edge_type,
    edge.weight = row.weight,
    edge.evidence_json = row.evidence_json,
    edge.source = row.source
"""

_HAS_RELEASE_QUERY = f"""
MATCH (node:{_NODE_LABEL} {{release_version: $release_version}})
RETURN count(node) > 0 AS exists
"""

_SEARCH_NODES_QUERY = f"""
MATCH (node:{_NODE_LABEL} {{release_version: $release_version}})
WHERE ($search_query = ''
       OR toLower(node.title) CONTAINS toLower($search_query)
       OR toLower(node.node_id) CONTAINS toLower($search_query))
  AND ($node_type = '' OR node.node_type = $node_type)
RETURN node.node_id AS node_id,
       node.node_type AS node_type,
       node.title AS title,
       node.description AS description,
       node.payload_json AS payload_json,
       node.source AS source,
       node.confidence AS confidence,
       node.release_version AS release_version
ORDER BY node.node_type, node.title, node.node_id
SKIP $offset
LIMIT $limit
"""

_COUNT_NODES_QUERY = f"""
MATCH (node:{_NODE_LABEL} {{release_version: $release_version}})
WHERE ($search_query = ''
       OR toLower(node.title) CONTAINS toLower($search_query)
       OR toLower(node.node_id) CONTAINS toLower($search_query))
  AND ($node_type = '' OR node.node_type = $node_type)
RETURN count(node) AS total
"""

_LIST_RELEASE_VERSIONS_QUERY = f"""
MATCH (node:{_NODE_LABEL})
RETURN DISTINCT node.release_version AS release_version
ORDER BY release_version DESC
"""

_LIST_BUSINESS_RELEASE_VERSIONS_QUERY = f"""
MATCH (node:{_NODE_LABEL})
WHERE node.node_type IN $business_node_types
RETURN DISTINCT node.release_version AS release_version
ORDER BY release_version DESC
"""

_LIST_TECHNICAL_RELEASE_VERSIONS_QUERY = f"""
MATCH (node:{_NODE_LABEL})
WHERE node.node_type IN $technical_node_types
RETURN DISTINCT node.release_version AS release_version
ORDER BY release_version DESC
"""

_COUNT_RELEASE_QUERY = f"""
MATCH (node:{_NODE_LABEL} {{release_version: $release_version}})
WITH count(node) AS node_count
OPTIONAL MATCH ()-[edge:{_EDGE_TYPE} {{release_version: $release_version}}]->()
RETURN node_count, count(edge) AS edge_count
"""

_LIST_RELEASE_NODES_QUERY = f"""
MATCH (node:{_NODE_LABEL} {{release_version: $release_version}})
RETURN node.node_id AS node_id,
       node.node_type AS node_type,
       node.title AS title,
       node.description AS description,
       node.payload_json AS payload_json,
       node.source AS source,
       node.confidence AS confidence,
       node.release_version AS release_version
ORDER BY node.node_id
"""

_LIST_RELEASE_EDGES_QUERY = f"""
MATCH ()-[edge:{_EDGE_TYPE} {{release_version: $release_version}}]->()
RETURN edge.edge_id AS edge_id,
       edge.source_node_id AS source_node_id,
       edge.target_node_id AS target_node_id,
       edge.edge_type AS edge_type,
       edge.weight AS weight,
       edge.evidence_json AS evidence_json,
       edge.source AS source,
       edge.release_version AS release_version
ORDER BY edge.edge_id
"""

_SCHEMA_QUERIES = (
    f"CREATE INDEX knowledge_graph_node_release IF NOT EXISTS "
    f"FOR (node:{_NODE_LABEL}) ON (node.release_version)",
    f"CREATE INDEX knowledge_graph_node_id IF NOT EXISTS "
    f"FOR (node:{_NODE_LABEL}) ON (node.node_id)",
    f"CREATE INDEX knowledge_graph_edge_release IF NOT EXISTS "
    f"FOR ()-[edge:{_EDGE_TYPE}]-() ON (edge.release_version)",
)

_SEED_NODES_QUERY = f"""
MATCH (node:{_NODE_LABEL})
WHERE node.release_version = $release_version
  AND node.node_id IN $seed_node_ids
RETURN node.node_id AS node_id,
       node.node_type AS node_type,
       node.title AS title,
       node.description AS description,
       node.payload_json AS payload_json,
       node.source AS source,
       node.confidence AS confidence,
       node.release_version AS release_version
ORDER BY node.node_id
LIMIT $max_nodes
"""

_EXPAND_PATHS_QUERY = f"""
MATCH path=(seed:{_NODE_LABEL})-[:{_EDGE_TYPE}*1..2]->(target:{_NODE_LABEL})
WHERE seed.release_version = $release_version
  AND seed.node_id IN $seed_node_ids
  AND length(path) <= $max_hops
  AND all(node IN nodes(path) WHERE node.release_version = $release_version)
  AND all(edge IN relationships(path)
          WHERE edge.release_version = $release_version
            AND edge.edge_type IN $allowed_edge_types)
RETURN [node IN nodes(path) | {{
           node_id: node.node_id,
           node_type: node.node_type,
           title: node.title,
           description: node.description,
           payload_json: node.payload_json,
           source: node.source,
           confidence: node.confidence,
           release_version: node.release_version
       }}] AS nodes,
       [edge IN relationships(path) | {{
           edge_id: edge.edge_id,
           source_node_id: edge.source_node_id,
           target_node_id: edge.target_node_id,
           edge_type: edge.edge_type,
           weight: edge.weight,
           evidence_json: edge.evidence_json,
           source: edge.source,
           release_version: edge.release_version
       }}] AS edges,
       reduce(score = 1.0, edge IN relationships(path) |
              score * edge.weight) AS score
ORDER BY score DESC
LIMIT $max_paths
"""


class Neo4jKnowledgeGraphRepository:
    """负责按元数据版本读写 Neo4j 图谱。"""

    def __init__(
        self, driver: AsyncDriver, database: str, release_version: str | None = None
    ):
        self.driver = driver
        self.database = database
        self.release_version = release_version or "legacy"

    def set_release_version(self, release_version: str | None) -> None:
        """切换当前仓储默认读取版本。"""

        self.release_version = release_version or "legacy"

    async def ensure_schema(self) -> None:
        """创建图谱查询所需的版本和实体索引。"""

        for query in _SCHEMA_QUERIES:
            await self._execute(query)

    async def clear_release(self, release_version: str | None = None) -> None:
        """清理指定版本的边和节点。"""

        version = release_version or self.release_version
        self._validate_release_version(version)

        async def clear(transaction: AsyncManagedTransaction) -> None:
            await (
                await transaction.run(_CLEAR_EDGES_QUERY, release_version=version)
            ).consume()
            await (
                await transaction.run(_CLEAR_NODES_QUERY, release_version=version)
            ).consume()

        await self._run_transaction(clear)

    async def replace_release(
        self,
        release_version: str,
        nodes: list[KnowledgeGraphNode],
        edges: list[KnowledgeGraphEdge],
    ) -> None:
        """在一个 Neo4j 事务内完整替换指定发布版本。"""

        self._validate_release_rows(release_version, nodes, edges)
        node_rows = [self._node_row(node) for node in nodes]
        edge_rows = [self._edge_row(edge) for edge in edges]

        async def replace(transaction: AsyncManagedTransaction) -> None:
            await (
                await transaction.run(
                    _CLEAR_EDGES_QUERY, release_version=release_version
                )
            ).consume()
            await (
                await transaction.run(
                    _CLEAR_NODES_QUERY, release_version=release_version
                )
            ).consume()
            await (
                await transaction.run(
                    _WRITE_NODES_QUERY,
                    release_version=release_version,
                    nodes=node_rows,
                )
            ).consume()
            if edge_rows:
                await (
                    await transaction.run(
                        _WRITE_EDGES_QUERY,
                        release_version=release_version,
                        edges=edge_rows,
                    )
                ).consume()

        await self._run_transaction(replace)

    async def has_release(self, release_version: str | None = None) -> bool:
        """判断指定版本是否至少存在一个图谱节点。"""

        version = release_version or self.release_version
        self._validate_release_version(version)
        records = await self._execute(
            _HAS_RELEASE_QUERY,
            release_version=version,
        )
        return bool(records and records[0].get("exists"))

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

        params = {
            "release_version": release_version,
            "search_query": query.strip(),
            "node_type": node_type or "",
            "limit": limit,
            "offset": offset,
        }
        records = await self._execute(_SEARCH_NODES_QUERY, **params)
        count_records = await self._execute(_COUNT_NODES_QUERY, **params)
        total = int(count_records[0].get("total", 0)) if count_records else 0
        return [self._node_entity(record) for record in records], total

    async def list_release_versions(self) -> list[str]:
        """返回 Neo4j 中实际已物化的图谱版本。"""

        records = await self._execute(_LIST_RELEASE_VERSIONS_QUERY)
        return [record["release_version"] for record in records]

    async def list_business_release_versions(self) -> list[str]:
        """返回 Neo4j 中包含业务节点的图谱版本。"""

        records = await self._execute(
            _LIST_BUSINESS_RELEASE_VERSIONS_QUERY,
            business_node_types=list(BUSINESS_NODE_TYPES),
        )
        return [record["release_version"] for record in records]

    async def list_technical_release_versions(self) -> list[str]:
        """返回 Neo4j 中包含技术节点的图谱版本。"""

        records = await self._execute(
            _LIST_TECHNICAL_RELEASE_VERSIONS_QUERY,
            technical_node_types=list(TECHNICAL_NODE_TYPES),
        )
        return [record["release_version"] for record in records]

    async def count_release(
        self, release_version: str | None = None
    ) -> tuple[int, int]:
        """返回指定版本的节点数和边数。"""

        version = release_version or self.release_version
        self._validate_release_version(version)
        records = await self._execute(
            _COUNT_RELEASE_QUERY,
            release_version=version,
        )
        if not records:
            return 0, 0
        return int(records[0].get("node_count", 0)), int(
            records[0].get("edge_count", 0)
        )

    async def list_release(
        self, release_version: str
    ) -> tuple[list[KnowledgeGraphNode], list[KnowledgeGraphEdge]]:
        """读取指定版本的完整图谱，供管理视图做安全聚合。"""

        self._validate_release_version(release_version)
        node_records = await self._execute(
            _LIST_RELEASE_NODES_QUERY,
            release_version=release_version,
        )
        edge_records = await self._execute(
            _LIST_RELEASE_EDGES_QUERY,
            release_version=release_version,
        )
        return (
            [self._node_entity(record) for record in node_records],
            [self._edge_entity(record) for record in edge_records],
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
        """按边白名单对指定版本做有界路径扩展。"""

        self._validate_release_version(release_version)
        self._validate_limits(max_hops, max_nodes, max_paths)
        unknown_edge_types = allowed_edge_types - EDGE_TYPES
        if unknown_edge_types:
            raise ValueError(
                "unsupported edge types: " + ", ".join(sorted(unknown_edge_types))
            )
        if not seed_node_ids:
            return [], [], []

        params = {
            "release_version": release_version,
            "seed_node_ids": list(dict.fromkeys(seed_node_ids)),
            "allowed_edge_types": sorted(allowed_edge_types),
            "max_hops": max_hops,
            "max_nodes": max_nodes,
            "max_paths": max_paths,
        }
        seed_records = await self._execute(_SEED_NODES_QUERY, **params)
        path_records = await self._execute(_EXPAND_PATHS_QUERY, **params)

        node_map: dict[str, KnowledgeGraphNode] = {}
        node_order: list[str] = []
        edge_map: dict[str, KnowledgeGraphEdge] = {}
        paths: list[KnowledgeGraphPath] = []

        for record in seed_records:
            node = self._node_entity(record)
            self._add_node(node_map, node_order, node)

        for record in path_records:
            path_nodes = [self._node_entity(row) for row in record.get("nodes", [])]
            new_node_ids = [
                node.node_id for node in path_nodes if node.node_id not in node_map
            ]
            if len(node_map) + len(new_node_ids) > max_nodes:
                continue
            for node in path_nodes:
                self._add_node(node_map, node_order, node)

            path_edges = [self._edge_entity(row) for row in record.get("edges", [])]
            for edge in path_edges:
                edge_map[edge.edge_id] = edge
            node_ids = tuple(node.node_id for node in path_nodes)
            edge_ids = tuple(edge.edge_id for edge in path_edges)
            paths.append(
                KnowledgeGraphPath(
                    node_ids=node_ids,
                    edge_ids=edge_ids,
                    score=float(record.get("score", 0.0)),
                )
            )
            if len(paths) >= max_paths:
                break

        return (
            [node_map[node_id] for node_id in node_order],
            sorted(edge_map.values(), key=lambda edge: edge.edge_id),
            paths,
        )

    async def _run_transaction(
        self,
        operation: Callable[[AsyncManagedTransaction], Awaitable[None]],
    ) -> None:
        async with self.driver.session(database=self.database) as session:
            async with await session.begin_transaction() as transaction:
                await operation(transaction)

    async def _execute(self, query: str, **parameters: Any) -> list[Any]:
        result = await self.driver.execute_query(
            query,
            database_=self.database,
            **parameters,
        )
        if isinstance(result, tuple):
            return list(result[0])
        return list(result)

    @staticmethod
    def _validate_release_version(release_version: str) -> None:
        if not release_version.strip():
            raise ValueError("release_version must not be empty")

    @staticmethod
    def _validate_limits(max_hops: int, max_nodes: int, max_paths: int) -> None:
        if not 1 <= max_hops <= 2:
            raise ValueError("max_hops must be between 1 and 2")
        if max_nodes < 1:
            raise ValueError("max_nodes must be positive")
        if max_paths < 1:
            raise ValueError("max_paths must be positive")

    @classmethod
    def _validate_release_rows(
        cls,
        release_version: str,
        nodes: list[KnowledgeGraphNode],
        edges: list[KnowledgeGraphEdge],
    ) -> None:
        cls._validate_release_version(release_version)
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
    def _node_row(node: KnowledgeGraphNode) -> dict[str, object]:
        return {
            "node_id": node.node_id,
            "node_type": node.node_type,
            "title": node.title,
            "description": node.description,
            "payload_json": json.dumps(
                node.payload, ensure_ascii=False, sort_keys=True
            ),
            "source": node.source,
            "confidence": node.confidence,
            "release_version": node.release_version,
        }

    @staticmethod
    def _edge_row(edge: KnowledgeGraphEdge) -> dict[str, object]:
        return {
            "edge_id": edge.edge_id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "edge_type": edge.edge_type,
            "weight": edge.weight,
            "evidence_json": json.dumps(
                edge.evidence, ensure_ascii=False, sort_keys=True
            ),
            "source": edge.source,
            "release_version": edge.release_version,
        }

    @classmethod
    def _node_entity(cls, row: Any) -> KnowledgeGraphNode:
        return KnowledgeGraphNode(
            node_id=row["node_id"],
            node_type=row["node_type"],
            title=row["title"],
            description=row["description"],
            payload=cls._json_object(row.get("payload_json")),
            source=row["source"],
            confidence=float(row["confidence"]),
            release_version=row["release_version"],
        )

    @classmethod
    def _edge_entity(cls, row: Any) -> KnowledgeGraphEdge:
        return KnowledgeGraphEdge(
            edge_id=row["edge_id"],
            source_node_id=row["source_node_id"],
            target_node_id=row["target_node_id"],
            edge_type=row["edge_type"],
            weight=float(row["weight"]),
            evidence=cls._json_object(row.get("evidence_json")),
            source=row["source"],
            release_version=row["release_version"],
        )

    @staticmethod
    def _json_object(value: object) -> dict[str, object]:
        if value is None:
            return {}
        if isinstance(value, str):
            decoded = json.loads(value)
        else:
            decoded = value
        if not isinstance(decoded, dict):
            raise ValueError("Neo4j graph JSON property must be an object")
        return dict(decoded)

    @staticmethod
    def _add_node(
        node_map: dict[str, KnowledgeGraphNode],
        node_order: list[str],
        node: KnowledgeGraphNode,
    ) -> None:
        if node.node_id not in node_map:
            node_map[node.node_id] = node
            node_order.append(node.node_id)
