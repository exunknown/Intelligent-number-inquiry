"""知识图谱管理页查询服务。"""

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from app.api.schemas.knowledge_graph_schema import (
    KnowledgeGraphEvidenceResponse,
    KnowledgeGraphGraphResponse,
    KnowledgeGraphOntologyRelationResponse,
    KnowledgeGraphOntologyResponse,
    KnowledgeGraphOntologyTypeResponse,
)
from app.entities.knowledge_graph import (
    BUSINESS_EDGE_TYPES,
    BUSINESS_NODE_TYPES,
    EDGE_TYPES,
    TECHNICAL_EDGE_TYPES,
    TECHNICAL_NODE_TYPES,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    KnowledgeGraphPath,
)
from app.repositories.mysql.meta.metadata_release_repository import (
    MetadataReleaseRepository,
)

KnowledgeGraphBackend = Literal["mysql", "neo4j"]
KnowledgeGraphReleaseScope = Literal["business", "technical", "all"]


class KnowledgeGraphReleaseNotFoundError(ValueError):
    """请求的元数据发布版本不存在。"""


class KnowledgeGraphNodeNotFoundError(ValueError):
    """请求的图谱种子节点不存在。"""


_TYPE_LABELS = {
    "table": ("数据表", "可查询的物理或逻辑数据表"),
    "column": ("字段", "数据表中的字段"),
    "cube": ("Cube", "受治理的语义数据集"),
    "semantic_member": ("语义成员", "Cube 中可被问数使用的维度或指标"),
    "metric_equivalence_group": ("指标等效组", "语义上可互换的指标集合"),
    "business_term": ("业务术语", "面向业务用户的术语和别名"),
    "value": ("字段取值", "字段的安全示例取值"),
    "customer_segment": ("客户群体", "按会员等级聚合的客户群体"),
    "customer": ("客户", "脱敏后的客户实体"),
    "product": ("商品", "电商商品实体"),
    "category": ("品类", "商品分类实体"),
    "brand": ("品牌", "商品品牌实体"),
    "region": ("区域", "销售区域实体"),
    "metric": ("经营指标", "业务经营指标"),
    "time_period": ("时间周期", "订单聚合统计周期"),
}

_RELATION_LABELS = {
    "TABLE_HAS_COLUMN": ("包含字段", ["table"], ["column"]),
    "COLUMN_BELONGS_TO_TABLE": ("字段属于表", ["column"], ["table"]),
    "COLUMN_REFERENCES_COLUMN": ("字段引用", ["column"], ["column"]),
    "CUBE_ON_TABLE": ("Cube 基于表", ["cube"], ["table"]),
    "CUBE_JOIN_CUBE": ("Cube 关联", ["cube"], ["cube"]),
    "MEMBER_IN_CUBE": ("成员属于 Cube", ["semantic_member"], ["cube"]),
    "MEMBER_SOURCE_COLUMN": ("成员来源字段", ["semantic_member"], ["column"]),
    "MEASURE_DEPENDS_ON_MEMBER": (
        "指标依赖成员",
        ["semantic_member"],
        ["semantic_member"],
    ),
    "METRIC_EQUIVALENT_TO": ("指标等效", ["semantic_member"], ["semantic_member"]),
    "METRIC_ATTACHED_TO": ("指标附加关系", ["semantic_member"], ["semantic_member"]),
    "TERM_ALIASES_MEMBER": ("术语别名", ["business_term"], ["semantic_member"]),
    "VALUE_BELONGS_TO_COLUMN": ("取值属于字段", ["value"], ["column"]),
    "CUSTOMER_IN_SEGMENT": ("客户属于群体", ["customer_segment"], ["customer"]),
    "CUSTOMER_PURCHASED_PRODUCT": ("客户购买商品", ["customer"], ["product"]),
    "SEGMENT_PREFERS_CATEGORY": ("群体偏好品类", ["customer_segment"], ["category"]),
    "SEGMENT_PREFERS_BRAND": ("群体偏好品牌", ["customer_segment"], ["brand"]),
    "PRODUCT_BELONGS_TO_CATEGORY": ("商品属于品类", ["product"], ["category"]),
    "PRODUCT_OF_BRAND": ("商品属于品牌", ["product"], ["brand"]),
    "PRODUCT_HOT_IN_REGION": ("商品热销区域", ["product"], ["region"]),
    "CATEGORY_CONTRIBUTES_TO_REGION": ("品类贡献区域", ["category"], ["region"]),
    "PRODUCT_ASSOCIATED_WITH_PRODUCT": ("商品关联购买", ["product"], ["product"]),
    "METRIC_MEASURES_OBJECT": ("指标度量对象", ["metric"], ["category"]),
    "METRIC_IN_PERIOD": ("指标属于周期", ["metric"], ["time_period"]),
}

_SCENARIO_TYPES = {
    "product": {"product", "category", "brand", "region", "metric"},
    "customer": {"customer", "customer_segment", "product", "category", "brand"},
    "region": {"region", "product", "category", "brand", "metric"},
    "metric": {"metric", "category", "time_period", "product", "region"},
}


@dataclass(frozen=True)
class KnowledgeGraphQueryService:
    """为 Agent 管理页提供版本、节点和有界子图查询。"""

    graph_repository: object
    metadata_release_repository: MetadataReleaseRepository
    backend: KnowledgeGraphBackend

    async def _list_business_release_versions(self) -> list[str]:
        list_versions = (
            getattr(
                self.graph_repository,
                "list_business_release_versions",
                None,
            )
            or self.graph_repository.list_release_versions
        )
        return await list_versions()

    async def _list_release_versions(
        self, scope: KnowledgeGraphReleaseScope
    ) -> list[str]:
        if scope == "business":
            return await self._list_business_release_versions()
        if scope == "technical":
            list_versions = (
                getattr(
                    self.graph_repository,
                    "list_technical_release_versions",
                    None,
                )
                or self.graph_repository.list_release_versions
            )
            return await list_versions()
        return await self.graph_repository.list_release_versions()

    async def list_releases(self) -> tuple[list[dict], str | None]:
        graph_versions = await self.graph_repository.list_release_versions()
        metadata_records = {
            record["release_version"]: record
            for record in await self.metadata_release_repository.list_releases()
        }
        # 图谱有独立的物化顺序，不能用 Cube/元数据 active 版本覆盖它。
        business_graph_versions = await self._list_business_release_versions()
        active_version = business_graph_versions[0] if business_graph_versions else None
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
        scope = (
            "business"
            if node_type in BUSINESS_NODE_TYPES
            else "technical"
            if node_type in TECHNICAL_NODE_TYPES
            else "all"
        )
        version = await self._resolve_release(release_version, scope=scope)
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
        seed_type = seed_node_id.split(":", 1)[0]
        scope = (
            "business"
            if seed_type in BUSINESS_NODE_TYPES
            else "technical"
            if seed_type in TECHNICAL_NODE_TYPES
            else "all"
        )
        version = await self._resolve_release(release_version, scope=scope)
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

    async def get_ontology(
        self,
        release_version: str | None,
        scope: Literal["business", "schema", "all"],
    ) -> KnowledgeGraphOntologyResponse:
        """返回由白名单定义驱动的本体类型和关系计数。"""

        version = await self._resolve_release(
            release_version,
            scope="technical" if scope == "schema" else scope,
        )
        nodes, edges = await self.graph_repository.list_release(version)
        allowed_node_types, allowed_edge_types = self._scope_types(scope)
        node_counts = Counter(
            node.node_type for node in nodes if node.node_type in allowed_node_types
        )
        edge_counts = Counter(
            edge.edge_type for edge in edges if edge.edge_type in allowed_edge_types
        )
        object_types = [
            KnowledgeGraphOntologyTypeResponse(
                type_name=type_name,
                label=_TYPE_LABELS[type_name][0],
                description=_TYPE_LABELS[type_name][1],
                node_count=node_counts[type_name],
                relation_count=sum(
                    count
                    for relation, count in edge_counts.items()
                    if type_name
                    in (
                        _RELATION_LABELS.get(relation, (None, [], []))[1]
                        + _RELATION_LABELS.get(relation, (None, [], []))[2]
                    )
                ),
            )
            for type_name in sorted(allowed_node_types)
        ]
        relation_types = [
            KnowledgeGraphOntologyRelationResponse(
                relation_type=relation_type,
                label=_RELATION_LABELS[relation_type][0],
                description=f"{_RELATION_LABELS[relation_type][0]}关系",
                source_types=_RELATION_LABELS[relation_type][1],
                target_types=_RELATION_LABELS[relation_type][2],
                edge_count=edge_counts[relation_type],
            )
            for relation_type in sorted(allowed_edge_types)
        ]
        return KnowledgeGraphOntologyResponse(
            release_version=version,
            scope=scope,
            object_types=object_types,
            relation_types=relation_types,
            backend=self.backend,
        )

    async def get_graph(
        self,
        release_version: str | None,
        view: Literal["relation", "schema"],
        scenario: str | None,
        seed_node_id: str | None,
        object_types: set[str],
        relation_types: set[str],
        max_hops: int,
        max_nodes: int,
        max_edges: int,
        include_evidence: bool,
    ) -> KnowledgeGraphGraphResponse:
        """按视图白名单返回有界图谱和安全聚合证据。"""

        if max_hops not in {1, 2}:
            raise ValueError("max_hops must be between 1 and 2")
        if not 1 <= max_nodes <= 200:
            raise ValueError("max_nodes must be between 1 and 200")
        if not 1 <= max_edges <= 400:
            raise ValueError("max_edges must be between 1 and 400")
        if scenario is not None and scenario not in _SCENARIO_TYPES:
            raise ValueError("unsupported graph scenario")
        version = await self._resolve_release(
            release_version,
            scope="business" if view == "relation" else "technical",
        )
        allowed_node_types, allowed_edge_types = self._view_types(view)
        unknown_nodes = object_types - allowed_node_types
        unknown_edges = relation_types - allowed_edge_types
        if unknown_nodes or unknown_edges:
            raise ValueError("graph filters contain unsupported types")
        selected_node_types = object_types or allowed_node_types
        selected_edge_types = relation_types or allowed_edge_types
        all_nodes, _ = await self.graph_repository.list_release(version)
        filtered_nodes = [
            node for node in all_nodes if node.node_type in selected_node_types
        ]
        if seed_node_id:
            if not any(node.node_id == seed_node_id for node in filtered_nodes):
                raise KnowledgeGraphNodeNotFoundError(seed_node_id)
            seed_ids = [seed_node_id]
        else:
            preferred_types = _SCENARIO_TYPES.get(scenario or "product", set())
            seed_ids = [
                node.node_id
                for node in filtered_nodes
                if node.node_type in preferred_types
            ]
            if not seed_ids:
                seed_ids = [node.node_id for node in filtered_nodes]
            seed_ids = sorted(seed_ids)[: min(20, max_nodes)]
        nodes, edges, paths = await self.graph_repository.expand_paths(
            version,
            seed_ids,
            selected_edge_types,
            max_hops=max_hops,
            max_nodes=max_nodes,
            max_paths=min(200, max_nodes),
        )
        selected_node_ids = {
            node.node_id for node in nodes if node.node_type in selected_node_types
        }
        nodes = [node for node in nodes if node.node_id in selected_node_ids]
        edges = [
            edge
            for edge in edges
            if edge.source_node_id in selected_node_ids
            and edge.target_node_id in selected_node_ids
        ]
        selected_edge_ids = {edge.edge_id for edge in edges}
        paths = [
            path
            for path in paths
            if set(path.node_ids) <= selected_node_ids
            and set(path.edge_ids) <= selected_edge_ids
        ]
        partial = len(nodes) >= max_nodes or len(paths) >= min(200, max_nodes)
        if len(edges) > max_edges:
            edges = edges[:max_edges]
            edge_ids = {edge.edge_id for edge in edges}
            paths = [path for path in paths if set(path.edge_ids) <= edge_ids]
            partial = True
        return KnowledgeGraphGraphResponse(
            view=view,
            release_version=version,
            nodes=[self._safe_node_response(node) for node in nodes],
            edges=[self._safe_edge_response(edge) for edge in edges],
            paths=[self._path_response(path) for path in paths],
            evidence=(
                [self._evidence_response(edge) for edge in edges]
                if include_evidence
                else []
            ),
            partial=partial,
            backend=self.backend,
        )

    async def _resolve_release(
        self,
        release_version: str | None,
        *,
        scope: KnowledgeGraphReleaseScope = "all",
    ) -> str:
        if release_version:
            node_count, edge_count = await self.graph_repository.count_release(
                release_version
            )
            if node_count == 0 and edge_count == 0:
                raise KnowledgeGraphReleaseNotFoundError(release_version)
            return release_version

        graph_versions = await self._list_release_versions(scope)
        if graph_versions:
            return graph_versions[0]
        raise KnowledgeGraphReleaseNotFoundError("graph release not found")

    @staticmethod
    def _scope_types(scope: str) -> tuple[set[str], set[str]]:
        if scope == "business":
            return set(BUSINESS_NODE_TYPES), set(BUSINESS_EDGE_TYPES)
        if scope == "schema":
            return set(TECHNICAL_NODE_TYPES), set(TECHNICAL_EDGE_TYPES)
        if scope == "all":
            return set(BUSINESS_NODE_TYPES | TECHNICAL_NODE_TYPES), set(EDGE_TYPES)
        raise ValueError("unsupported ontology scope")

    @staticmethod
    def _view_types(view: str) -> tuple[set[str], set[str]]:
        if view == "relation":
            return set(BUSINESS_NODE_TYPES), set(BUSINESS_EDGE_TYPES)
        if view == "schema":
            return set(TECHNICAL_NODE_TYPES), set(TECHNICAL_EDGE_TYPES)
        raise ValueError("unsupported graph view")

    @classmethod
    def _safe_node_response(cls, node: KnowledgeGraphNode) -> dict[str, object]:
        return {
            "node_id": node.node_id,
            "node_type": node.node_type,
            "title": node.title,
            "description": node.description,
            "metadata": cls.safe_node_metadata(node),
            "source": node.source,
            "confidence": node.confidence,
            "release_version": node.release_version,
        }

    @staticmethod
    def _safe_edge_response(edge: KnowledgeGraphEdge) -> dict[str, object]:
        return {
            "edge_id": edge.edge_id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "edge_type": edge.edge_type,
            "weight": edge.weight,
            "source": edge.source,
            "release_version": edge.release_version,
        }

    @staticmethod
    def _path_response(path: KnowledgeGraphPath) -> dict[str, object]:
        return {
            "node_ids": list(path.node_ids),
            "edge_ids": list(path.edge_ids),
            "score": path.score,
        }

    @staticmethod
    def _evidence_response(edge: KnowledgeGraphEdge) -> KnowledgeGraphEvidenceResponse:
        evidence = edge.evidence
        source_refs = evidence.get("source_refs", [])
        if not isinstance(source_refs, list):
            source_refs = []
        safe_source_refs = [
            {
                str(key): value
                for key, value in item.items()
                if str(key)
                in {
                    "node_id",
                    "table_id",
                    "column_id",
                    "source",
                    "period",
                    "release_version",
                }
                and isinstance(value, (str, int, float, bool))
            }
            for item in source_refs
            if isinstance(item, dict)
        ]
        return KnowledgeGraphEvidenceResponse(
            edge_id=edge.edge_id,
            period=(
                str(evidence["period"]) if evidence.get("period") is not None else None
            ),
            order_count=(
                int(evidence["order_count"])
                if evidence.get("order_count") is not None
                else None
            ),
            sales_amount=(
                float(evidence["sales_amount"])
                if evidence.get("sales_amount") is not None
                else None
            ),
            share=(
                float(evidence["share"]) if evidence.get("share") is not None else None
            ),
            rank=(int(evidence["rank"]) if evidence.get("rank") is not None else None),
            confidence=(
                float(evidence["confidence"])
                if evidence.get("confidence") is not None
                else None
            ),
            source_refs=safe_source_refs,
        )

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
            "business_key",
        }
        if node.node_type == "customer":
            allowed_keys.remove("business_key")
        return {
            key: value for key, value in node.payload.items() if key in allowed_keys
        }
