"""从电商事实数据构建业务聚合知识图谱。"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from app.conf.app_config import KnowledgeGraphConfig
from app.entities.knowledge_graph import KnowledgeGraphEdge, KnowledgeGraphNode
from app.repositories.mysql.dw.business_graph_repository import (
    BusinessGraphSourceRepository,
    OrderGraphRow,
)
from app.services.knowledge_graph_service import GraphBuildResult, KnowledgeGraphService


@dataclass(frozen=True)
class _Aggregate:
    order_count: int
    quantity: int
    sales_amount: Decimal


class BusinessKnowledgeGraphService:
    """把订单事实聚合为稳定、可解释的电商业务节点和关系。"""

    def __init__(
        self,
        source_repository: BusinessGraphSourceRepository,
        config: KnowledgeGraphConfig,
        repository=None,
    ):
        self.source_repository = source_repository
        self.config = config
        self.repository = repository

    async def build(self, release_version: str) -> GraphBuildResult:
        if not release_version.strip():
            raise ValueError("release_version must not be empty")

        customers = await self.source_repository.load_customer_rows()
        orders = await self.source_repository.load_order_rows()
        customer_segments = {
            customer.customer_id: customer.member_level.strip() or "未分层"
            for customer in customers
        }
        nodes: dict[str, KnowledgeGraphNode] = {}
        edges: dict[str, KnowledgeGraphEdge] = {}

        for customer_id, member_level in sorted(customer_segments.items()):
            segment_id = self._node_id("customer_segment", member_level)
            self._add_node(
                nodes,
                self._node(
                    segment_id,
                    "customer_segment",
                    f"{member_level}会员",
                    "按会员等级形成的客户经营群体",
                    {"business_key": member_level},
                    release_version,
                ),
            )
            customer_id_value = self._node_id("customer", customer_id)
            self._add_node(
                nodes,
                self._node(
                    customer_id_value,
                    "customer",
                    self._mask_customer_id(customer_id),
                    "脱敏客户实体",
                    {"business_key": customer_id},
                    release_version,
                ),
            )
            self._add_edge(
                edges,
                self._edge(
                    "CUSTOMER_IN_SEGMENT",
                    segment_id,
                    customer_id_value,
                    release_version,
                    weight=1.0,
                    evidence={"member_level": member_level},
                ),
            )

        for row in sorted(orders, key=self._order_sort_key):
            self._add_order_nodes(nodes, row, release_version)

        self._add_product_edges(nodes, edges, orders, release_version)
        self._add_customer_product_edges(edges, orders, release_version)
        self._add_segment_preference_edges(
            nodes, edges, orders, customer_segments, release_version
        )
        self._add_region_edges(nodes, edges, orders, release_version)
        self._add_association_edges(nodes, edges, orders, release_version)
        self._add_metric_edges(nodes, edges, orders, release_version)

        result = GraphBuildResult(
            release_version,
            sorted(nodes.values(), key=lambda node: node.node_id),
            sorted(edges.values(), key=lambda edge: edge.edge_id),
        )
        KnowledgeGraphService.validate(result.nodes, result.edges, release_version)
        return result

    async def persist(self, build_result: GraphBuildResult) -> None:
        if self.repository is None:
            raise RuntimeError("knowledge graph repository is required")
        await self.repository.replace_release(
            build_result.release_version,
            build_result.nodes,
            build_result.edges,
        )

    def _add_order_nodes(
        self,
        nodes: dict[str, KnowledgeGraphNode],
        row: OrderGraphRow,
        release_version: str,
    ) -> None:
        self._add_node(
            nodes,
            self._node(
                self._node_id("product", row.product_id),
                "product",
                row.product_name,
                "电商商品",
                {"business_key": row.product_id},
                release_version,
            ),
        )
        self._add_node(
            nodes,
            self._node(
                self._node_id("category", row.category),
                "category",
                row.category,
                "商品品类",
                {"business_key": row.category},
                release_version,
            ),
        )
        self._add_node(
            nodes,
            self._node(
                self._node_id("brand", row.brand),
                "brand",
                row.brand,
                "商品品牌",
                {"business_key": row.brand},
                release_version,
            ),
        )
        self._add_node(
            nodes,
            self._node(
                self._node_id("region", row.region_id),
                "region",
                row.region_name,
                "销售区域",
                {"business_key": row.region_id},
                release_version,
            ),
        )

    def _add_product_edges(
        self,
        nodes: dict[str, KnowledgeGraphNode],
        edges: dict[str, KnowledgeGraphEdge],
        orders: list[OrderGraphRow],
        release_version: str,
    ) -> None:
        products: dict[str, OrderGraphRow] = {}
        for row in orders:
            products.setdefault(row.product_id, row)
        for row in products.values():
            product_id = self._node_id("product", row.product_id)
            category_id = self._node_id("category", row.category)
            brand_id = self._node_id("brand", row.brand)
            self._add_edge(
                edges,
                self._edge(
                    "PRODUCT_BELONGS_TO_CATEGORY",
                    product_id,
                    category_id,
                    release_version,
                    weight=1.0,
                    evidence={"category": row.category},
                ),
            )
            self._add_edge(
                edges,
                self._edge(
                    "PRODUCT_OF_BRAND",
                    product_id,
                    brand_id,
                    release_version,
                    weight=1.0,
                    evidence={"brand": row.brand},
                ),
            )

    def _add_customer_product_edges(
        self,
        edges: dict[str, KnowledgeGraphEdge],
        orders: list[OrderGraphRow],
        release_version: str,
    ) -> None:
        grouped: dict[tuple[str, str], list[OrderGraphRow]] = defaultdict(list)
        for row in orders:
            grouped[(row.customer_id, row.product_id)].append(row)
        for (customer_id, product_id), rows in sorted(grouped.items()):
            aggregate = self._aggregate(rows)
            self._add_edge(
                edges,
                self._edge(
                    "CUSTOMER_PURCHASED_PRODUCT",
                    self._node_id("customer", customer_id),
                    self._node_id("product", product_id),
                    release_version,
                    weight=self._confidence(aggregate.order_count, len(orders)),
                    evidence=self._aggregate_evidence(aggregate),
                ),
            )

    def _add_segment_preference_edges(
        self,
        nodes: dict[str, KnowledgeGraphNode],
        edges: dict[str, KnowledgeGraphEdge],
        orders: list[OrderGraphRow],
        customer_segments: dict[str, str],
        release_version: str,
    ) -> None:
        grouped: dict[tuple[str, str, str], list[OrderGraphRow]] = defaultdict(list)
        totals: dict[str, set[str]] = defaultdict(set)
        for row in orders:
            segment = customer_segments.get(row.customer_id, "未分层")
            totals[segment].add(row.order_id)
            grouped[(segment, "category", row.category)].append(row)
            grouped[(segment, "brand", row.brand)].append(row)
        for (segment, dimension_type, dimension), rows in sorted(grouped.items()):
            aggregate = self._aggregate(rows)
            if aggregate.order_count < self.config.min_order_count:
                continue
            edge_type = (
                "SEGMENT_PREFERS_CATEGORY"
                if dimension_type == "category"
                else "SEGMENT_PREFERS_BRAND"
            )
            target_type = dimension_type
            total_orders = max(len(totals[segment]), 1)
            self._add_edge(
                edges,
                self._edge(
                    edge_type,
                    self._node_id("customer_segment", segment),
                    self._node_id(target_type, dimension),
                    release_version,
                    weight=aggregate.order_count / total_orders,
                    evidence={
                        **self._aggregate_evidence(aggregate),
                        "share": aggregate.order_count / total_orders,
                    },
                ),
            )

    def _add_region_edges(
        self,
        nodes: dict[str, KnowledgeGraphNode],
        edges: dict[str, KnowledgeGraphEdge],
        orders: list[OrderGraphRow],
        release_version: str,
    ) -> None:
        product_regions: dict[tuple[str, str], list[OrderGraphRow]] = defaultdict(list)
        category_regions: dict[tuple[str, str], list[OrderGraphRow]] = defaultdict(list)
        for row in orders:
            product_regions[(row.product_id, row.region_id)].append(row)
            category_regions[(row.category, row.region_id)].append(row)
        for (product_id, region_id), rows in sorted(product_regions.items()):
            aggregate = self._aggregate(rows)
            self._add_edge(
                edges,
                self._edge(
                    "PRODUCT_HOT_IN_REGION",
                    self._node_id("product", product_id),
                    self._node_id("region", region_id),
                    release_version,
                    weight=aggregate.sales_amount or 1.0,
                    evidence=self._aggregate_evidence(aggregate),
                ),
            )
        for (category, region_id), rows in sorted(category_regions.items()):
            aggregate = self._aggregate(rows)
            self._add_edge(
                edges,
                self._edge(
                    "CATEGORY_CONTRIBUTES_TO_REGION",
                    self._node_id("category", category),
                    self._node_id("region", region_id),
                    release_version,
                    weight=aggregate.sales_amount or 1.0,
                    evidence=self._aggregate_evidence(aggregate),
                ),
            )

    def _add_association_edges(
        self,
        nodes: dict[str, KnowledgeGraphNode],
        edges: dict[str, KnowledgeGraphEdge],
        orders: list[OrderGraphRow],
        release_version: str,
    ) -> None:
        by_order: dict[str, list[OrderGraphRow]] = defaultdict(list)
        for row in orders:
            by_order[row.order_id].append(row)
        pairs: dict[tuple[str, str], int] = defaultdict(int)
        for rows in by_order.values():
            product_ids = sorted({row.product_id for row in rows})
            for source_id, target_id in combinations(product_ids, 2):
                pairs[(source_id, target_id)] += 1
        by_source: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for (source_id, target_id), order_count in pairs.items():
            if order_count >= self.config.min_order_count:
                by_source[source_id].append((target_id, order_count))
        for source_id, targets in sorted(by_source.items()):
            for target_id, order_count in sorted(
                targets, key=lambda item: (-item[1], item[0])
            )[: self.config.max_associations_per_product]:
                self._add_edge(
                    edges,
                    self._edge(
                        "PRODUCT_ASSOCIATED_WITH_PRODUCT",
                        self._node_id("product", source_id),
                        self._node_id("product", target_id),
                        release_version,
                        weight=float(order_count),
                        evidence={"order_count": order_count},
                    ),
                )

    def _add_metric_edges(
        self,
        nodes: dict[str, KnowledgeGraphNode],
        edges: dict[str, KnowledgeGraphEdge],
        orders: list[OrderGraphRow],
        release_version: str,
    ) -> None:
        metric_ids = {"sales_amount": "销售额", "order_count": "订单数"}
        periods = sorted({self._period(row.date_id) for row in orders})
        for metric_key, title in metric_ids.items():
            metric_id = self._node_id("metric", metric_key)
            self._add_node(
                nodes,
                self._node(
                    metric_id,
                    "metric",
                    title,
                    "电商经营指标",
                    {"business_key": metric_key},
                    release_version,
                ),
            )
            for period in periods:
                period_id = self._node_id("time_period", period)
                self._add_node(
                    nodes,
                    self._node(
                        period_id,
                        "time_period",
                        period,
                        "订单统计周期",
                        {"business_key": period},
                        release_version,
                    ),
                )
                self._add_edge(
                    edges,
                    self._edge(
                        "METRIC_IN_PERIOD",
                        metric_id,
                        period_id,
                        release_version,
                        weight=1.0,
                        evidence={"metric": metric_key},
                    ),
                )
            for category in sorted({row.category for row in orders}):
                rows = [row for row in orders if row.category == category]
                aggregate = self._aggregate(rows)
                self._add_edge(
                    edges,
                    self._edge(
                        "METRIC_MEASURES_OBJECT",
                        metric_id,
                        self._node_id("category", category),
                        release_version,
                        weight=(
                            float(aggregate.sales_amount)
                            if metric_key == "sales_amount"
                            else float(aggregate.order_count)
                        ),
                        evidence={
                            "metric": metric_key,
                            **self._aggregate_evidence(aggregate),
                        },
                    ),
                )

    @staticmethod
    def _aggregate(rows: list[OrderGraphRow]) -> _Aggregate:
        return _Aggregate(
            order_count=len({row.order_id for row in rows}),
            quantity=sum(row.order_quantity for row in rows),
            sales_amount=sum((row.order_amount for row in rows), Decimal("0")),
        )

    @staticmethod
    def _aggregate_evidence(aggregate: _Aggregate) -> dict[str, object]:
        return {
            "order_count": aggregate.order_count,
            "quantity": aggregate.quantity,
            "sales_amount": float(aggregate.sales_amount),
        }

    @staticmethod
    def _confidence(order_count: int, total: int) -> float:
        return order_count / max(total, 1)

    @staticmethod
    def _period(date_id: int) -> str:
        text = str(date_id)
        return f"{text[:4]}-{text[4:6]}"

    @staticmethod
    def _mask_customer_id(customer_id: str) -> str:
        if len(customer_id) <= 2:
            return "客户 ***"
        return f"客户 {customer_id[0]}***{customer_id[-2:]}"

    @staticmethod
    def _order_sort_key(row: OrderGraphRow) -> tuple[str, str, int]:
        return row.order_id, row.product_id, row.date_id

    @staticmethod
    def _node_id(node_type: str, value: str) -> str:
        prefixes = {
            "customer_segment": "segment:",
            "customer": "customer:",
            "product": "product:",
            "category": "category:",
            "brand": "brand:",
            "region": "region:",
            "metric": "metric:",
            "time_period": "period:",
        }
        return f"{prefixes[node_type]}{value}"

    @staticmethod
    def _node(
        node_id: str,
        node_type: str,
        title: str,
        description: str,
        payload: dict[str, object],
        release_version: str,
    ) -> KnowledgeGraphNode:
        return KnowledgeGraphNode(
            node_id=node_id,
            node_type=node_type,
            title=title,
            description=description,
            payload=payload,
            source="business",
            confidence=1.0,
            release_version=release_version,
        )

    @staticmethod
    def _edge(
        edge_type: str,
        source_node_id: str,
        target_node_id: str,
        release_version: str,
        *,
        weight: float,
        evidence: dict[str, object],
    ) -> KnowledgeGraphEdge:
        return KnowledgeGraphEdge(
            edge_id=f"edge:{edge_type.lower()}:{source_node_id}->{target_node_id}",
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_type=edge_type,
            weight=max(float(weight), 0.000001),
            evidence=evidence,
            source="business",
            release_version=release_version,
        )

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
