"""元数据知识图谱构建和校验服务。"""

import re
from dataclasses import dataclass

from app.entities.column_info import ColumnInfo
from app.entities.knowledge_graph import (
    EDGE_TYPES,
    NODE_TYPES,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
)
from app.entities.semantic_model import SemanticModelSnapshot
from app.entities.table_info import TableInfo
from app.repositories.mysql.meta.knowledge_graph_repository import (
    KnowledgeGraphRepository,
)


@dataclass(frozen=True)
class GraphBuildResult:
    """一次图谱构建得到的稳定节点和边。"""

    release_version: str
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)


class KnowledgeGraphService:
    """从元数据和语义模型快照构建版本化知识图谱。"""

    def __init__(self, repository: KnowledgeGraphRepository | None = None):
        self.repository = repository

    async def build(
        self,
        table_infos: list[TableInfo],
        column_infos: list[ColumnInfo],
        snapshot: SemanticModelSnapshot | None,
        release_version: str,
    ) -> GraphBuildResult:
        """构建并校验一个发布版本的图谱，不执行持久化。"""

        if not release_version.strip():
            raise ValueError("release_version must not be empty")
        if snapshot is not None and snapshot.release_version != release_version:
            raise ValueError("semantic snapshot release_version does not match")

        nodes: dict[str, KnowledgeGraphNode] = {}
        edges: dict[str, KnowledgeGraphEdge] = {}

        for table in table_infos:
            self._add_node(
                nodes,
                KnowledgeGraphNode(
                    node_id=f"table:{table.id}",
                    node_type="table",
                    title=table.name,
                    description=table.description,
                    payload={"role": table.role},
                    source="metadata",
                    confidence=1.0,
                    release_version=release_version,
                ),
            )
        for column in column_infos:
            self._add_node(
                nodes,
                KnowledgeGraphNode(
                    node_id=f"column:{column.id}",
                    node_type="column",
                    title=column.name,
                    description=column.description,
                    payload={
                        "table_id": column.table_id,
                        "type": column.type,
                        "role": column.role,
                        "alias": list(column.alias),
                    },
                    source="metadata",
                    confidence=1.0,
                    release_version=release_version,
                ),
            )
            table_node_id = f"table:{column.table_id}"
            if table_node_id in nodes:
                self._add_edge(
                    edges,
                    self._edge(
                        "TABLE_HAS_COLUMN",
                        table_node_id,
                        f"column:{column.id}",
                        release_version,
                        weight=1.0,
                    ),
                )
                self._add_edge(
                    edges,
                    self._edge(
                        "COLUMN_BELONGS_TO_TABLE",
                        f"column:{column.id}",
                        table_node_id,
                        release_version,
                        weight=1.0,
                    ),
                )

        if snapshot is not None:
            self._add_semantic_graph(snapshot, release_version, nodes, edges)

        result_nodes = sorted(nodes.values(), key=lambda node: node.node_id)
        result_edges = sorted(edges.values(), key=lambda edge: edge.edge_id)
        self.validate(result_nodes, result_edges, release_version)
        return GraphBuildResult(release_version, result_nodes, result_edges)

    async def persist(self, build_result: GraphBuildResult) -> None:
        """将一个已校验的版本完整替换写入图谱仓储。"""

        if self.repository is None:
            raise RuntimeError("knowledge graph repository is required")
        await self.repository.replace_release(
            build_result.release_version,
            build_result.nodes,
            build_result.edges,
        )

    @staticmethod
    def validate(
        nodes: list[KnowledgeGraphNode],
        edges: list[KnowledgeGraphEdge],
        release_version: str,
    ) -> None:
        """校验版本一致性、类型白名单、重复项和边端点。"""

        node_by_id: dict[str, KnowledgeGraphNode] = {}
        for node in nodes:
            if node.release_version != release_version:
                raise ValueError("node release_version does not match")
            if node.node_type not in NODE_TYPES:
                raise ValueError(f"unsupported node_type: {node.node_type}")
            previous = node_by_id.get(node.node_id)
            if previous is not None and previous != node:
                raise ValueError(
                    f"duplicate node with conflicting payload: {node.node_id}"
                )
            node_by_id[node.node_id] = node

        edge_by_id: dict[str, KnowledgeGraphEdge] = {}
        for edge in edges:
            if edge.release_version != release_version:
                raise ValueError("edge release_version does not match")
            if edge.edge_type not in EDGE_TYPES:
                raise ValueError(f"unsupported edge_type: {edge.edge_type}")
            if (
                edge.source_node_id not in node_by_id
                or edge.target_node_id not in node_by_id
            ):
                raise ValueError(f"dangling edge: {edge.edge_id}")
            previous = edge_by_id.get(edge.edge_id)
            if previous is not None and previous != edge:
                raise ValueError(
                    f"duplicate edge with conflicting endpoints: {edge.edge_id}"
                )
            edge_by_id[edge.edge_id] = edge

    def _add_semantic_graph(
        self,
        snapshot: SemanticModelSnapshot,
        release_version: str,
        nodes: dict[str, KnowledgeGraphNode],
        edges: dict[str, KnowledgeGraphEdge],
    ) -> None:
        cube_ids = {cube.cube_name: f"cube:{cube.cube_name}" for cube in snapshot.cubes}
        for cube in snapshot.cubes:
            cube_node_id = cube_ids[cube.cube_name]
            self._add_node(
                nodes,
                KnowledgeGraphNode(
                    node_id=cube_node_id,
                    node_type="cube",
                    title=cube.title,
                    description=cube.description,
                    payload={"cube_name": cube.cube_name, "table": cube.sql_table},
                    source="semantic",
                    confidence=1.0,
                    release_version=release_version,
                ),
            )
            table_name = cube.sql_table.rsplit(".", 1)[-1]
            table_node_id = f"table:{table_name}"
            if table_node_id in nodes:
                self._add_edge(
                    edges,
                    self._edge(
                        "CUBE_ON_TABLE",
                        cube_node_id,
                        table_node_id,
                        release_version,
                        weight=1.0,
                    ),
                )

        member_nodes: dict[str, str] = {}
        for member in snapshot.members:
            node_id = f"member:{member.member_id}"
            member_nodes[member.member_id] = node_id
            self._add_node(
                nodes,
                KnowledgeGraphNode(
                    node_id=node_id,
                    node_type="semantic_member",
                    title=member.title,
                    description=member.description,
                    payload={
                        "member_id": member.member_id,
                        "cube_name": member.cube_name,
                        "member_name": member.member_name,
                        "member_type": member.member_type,
                        "source_column_id": member.source_column_id,
                        "aliases": list(member.aliases),
                    },
                    source="semantic",
                    confidence=1.0,
                    release_version=release_version,
                ),
            )
            cube_node_id = cube_ids.get(member.cube_name)
            if cube_node_id is not None:
                self._add_edge(
                    edges,
                    self._edge(
                        "MEMBER_IN_CUBE",
                        node_id,
                        cube_node_id,
                        release_version,
                        weight=1.0,
                    ),
                )
            if member.source_column_id and f"column:{member.source_column_id}" in nodes:
                self._add_edge(
                    edges,
                    self._edge(
                        "MEMBER_SOURCE_COLUMN",
                        node_id,
                        f"column:{member.source_column_id}",
                        release_version,
                        weight=1.0,
                    ),
                )
            for term in self._member_terms(
                member.title, member.aliases, member.ai_context
            ):
                term_node_id = f"term:{term}"
                self._add_node(
                    nodes,
                    KnowledgeGraphNode(
                        node_id=term_node_id,
                        node_type="business_term",
                        title=term,
                        description="语义成员业务术语",
                        payload={"value": term},
                        source="semantic",
                        confidence=0.8,
                        release_version=release_version,
                    ),
                )
                self._add_edge(
                    edges,
                    self._edge(
                        "TERM_ALIASES_MEMBER",
                        term_node_id,
                        node_id,
                        release_version,
                        weight=0.8,
                    ),
                )

        for member in snapshot.members:
            if member.measure is None:
                continue
            source_id = member_nodes[member.member_id]
            for dependency_id in member.measure.dependency_members:
                dependency_node_id = member_nodes.get(dependency_id)
                if dependency_node_id is not None:
                    self._add_edge(
                        edges,
                        self._edge(
                            "MEASURE_DEPENDS_ON_MEMBER",
                            source_id,
                            dependency_node_id,
                            release_version,
                            weight=1.0,
                        ),
                    )

        for cube_join in snapshot.joins:
            source_id = cube_ids.get(cube_join.cube_name)
            target_id = cube_ids.get(cube_join.target_cube_name)
            if source_id is not None and target_id is not None:
                self._add_edge(
                    edges,
                    self._edge(
                        "CUBE_JOIN_CUBE",
                        source_id,
                        target_id,
                        release_version,
                        weight=0.9,
                        evidence={"relationship": cube_join.relationship},
                    ),
                )

        for group in snapshot.metric_equivalence_groups:
            self._add_node(
                nodes,
                KnowledgeGraphNode(
                    node_id=f"equivalence:{group.group_id}",
                    node_type="metric_equivalence_group",
                    title=group.group_name,
                    description=group.description,
                    payload={"canonical_member_id": group.canonical_member_id},
                    source="semantic",
                    confidence=1.0,
                    release_version=release_version,
                ),
            )
            member_ids = [
                member_nodes[item.member_id]
                for item in group.members
                if item.member_id in member_nodes
            ]
            canonical_id = member_nodes.get(group.canonical_member_id)
            if canonical_id is not None:
                for member_id in member_ids:
                    if member_id != canonical_id:
                        self._add_edge(
                            edges,
                            self._edge(
                                "METRIC_EQUIVALENT_TO",
                                canonical_id,
                                member_id,
                                release_version,
                                weight=1.0,
                            ),
                        )

        for attachment in snapshot.metric_attachments:
            source_id = member_nodes.get(attachment.primary_member_id)
            target_id = member_nodes.get(attachment.attached_member_id)
            if source_id is not None and target_id is not None:
                self._add_edge(
                    edges,
                    self._edge(
                        "METRIC_ATTACHED_TO",
                        source_id,
                        target_id,
                        release_version,
                        weight=0.8,
                        evidence={"relation_type": attachment.relation_type},
                    ),
                )

    @staticmethod
    def _member_terms(
        title: str, aliases: tuple[str, ...], ai_context: str
    ) -> list[str]:
        terms: list[str] = []
        for value in (title, *aliases, ai_context):
            normalized = re.sub(r"\s+", " ", value.strip().lower())
            if normalized and normalized not in terms:
                terms.append(normalized)
        return terms

    @staticmethod
    def _add_node(
        nodes: dict[str, KnowledgeGraphNode], node: KnowledgeGraphNode
    ) -> None:
        previous = nodes.get(node.node_id)
        if previous is not None and previous != node:
            raise ValueError(f"duplicate node with conflicting payload: {node.node_id}")
        nodes[node.node_id] = node

    @staticmethod
    def _add_edge(
        edges: dict[str, KnowledgeGraphEdge], edge: KnowledgeGraphEdge
    ) -> None:
        previous = edges.get(edge.edge_id)
        if previous is not None and previous != edge:
            raise ValueError(
                f"duplicate edge with conflicting endpoints: {edge.edge_id}"
            )
        edges[edge.edge_id] = edge

    @staticmethod
    def _edge(
        edge_type: str,
        source_node_id: str,
        target_node_id: str,
        release_version: str,
        *,
        weight: float,
        evidence: dict[str, object] | None = None,
    ) -> KnowledgeGraphEdge:
        edge_id = f"edge:{edge_type.lower()}:{source_node_id}->{target_node_id}"
        return KnowledgeGraphEdge(
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_type=edge_type,
            weight=weight,
            evidence=evidence or {},
            source="semantic"
            if edge_type not in {"TABLE_HAS_COLUMN", "COLUMN_BELONGS_TO_TABLE"}
            else "metadata",
            release_version=release_version,
        )
