"""知识图谱管理页的只读 API 模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KnowledgeGraphNodeType = Literal[
    "table",
    "column",
    "cube",
    "semantic_member",
    "metric_equivalence_group",
    "business_term",
    "value",
    "customer_segment",
    "customer",
    "product",
    "category",
    "brand",
    "region",
    "metric",
    "time_period",
]
KnowledgeGraphBusinessNodeType = Literal[
    "customer_segment",
    "customer",
    "product",
    "category",
    "brand",
    "region",
    "metric",
    "time_period",
]
KnowledgeGraphView = Literal["relation", "schema"]
KnowledgeGraphScenario = Literal["product", "customer", "region", "metric"]


class KnowledgeGraphNodeResponse(BaseModel):
    """对前端公开的安全节点投影。"""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: KnowledgeGraphNodeType
    title: str
    description: str
    metadata: dict[str, object] = Field(default_factory=dict)
    source: str
    confidence: float
    release_version: str


class KnowledgeGraphEdgeResponse(BaseModel):
    """对前端公开的安全关系投影。"""

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    weight: float
    source: str
    release_version: str


class KnowledgeGraphPathResponse(BaseModel):
    """图谱展开返回的有界路径。"""

    model_config = ConfigDict(extra="forbid")

    node_ids: list[str]
    edge_ids: list[str]
    score: float


class KnowledgeGraphReleaseResponse(BaseModel):
    """元数据发布版本及其图谱计数。"""

    model_config = ConfigDict(extra="forbid")

    release_version: str
    status: str
    active: bool
    created_at: datetime | None
    node_count: int
    edge_count: int


class KnowledgeGraphReleaseListResponse(BaseModel):
    items: list[KnowledgeGraphReleaseResponse]
    active_release_version: str | None
    backend: Literal["mysql", "neo4j"]


class KnowledgeGraphNodeListResponse(BaseModel):
    items: list[KnowledgeGraphNodeResponse]
    total: int
    release_version: str
    backend: Literal["mysql", "neo4j"]


class KnowledgeGraphSubgraphResponse(BaseModel):
    nodes: list[KnowledgeGraphNodeResponse]
    edges: list[KnowledgeGraphEdgeResponse]
    paths: list[KnowledgeGraphPathResponse]
    release_version: str
    backend: Literal["mysql", "neo4j"]
    partial: bool


class KnowledgeGraphOntologyTypeResponse(BaseModel):
    """本体类型的安全定义投影。"""

    model_config = ConfigDict(extra="forbid")

    type_name: str
    label: str
    description: str
    node_count: int
    relation_count: int


class KnowledgeGraphOntologyRelationResponse(BaseModel):
    """本体关系的安全定义投影。"""

    model_config = ConfigDict(extra="forbid")

    relation_type: str
    label: str
    description: str
    source_types: list[str]
    target_types: list[str]
    edge_count: int


class KnowledgeGraphOntologyResponse(BaseModel):
    """本体底座查询响应。"""

    model_config = ConfigDict(extra="forbid")

    release_version: str
    scope: Literal["business", "schema", "all"]
    object_types: list[KnowledgeGraphOntologyTypeResponse]
    relation_types: list[KnowledgeGraphOntologyRelationResponse]
    backend: Literal["mysql", "neo4j"]


class KnowledgeGraphEvidenceResponse(BaseModel):
    """关系图可展示的有限聚合证据。"""

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    period: str | None = None
    order_count: int | None = None
    sales_amount: float | None = None
    share: float | None = None
    rank: int | None = None
    confidence: float | None = None
    source_refs: list[dict[str, object]] = Field(default_factory=list)


class KnowledgeGraphGraphResponse(BaseModel):
    """关系图或 Schema 图谱的安全响应。"""

    model_config = ConfigDict(extra="forbid")

    view: KnowledgeGraphView
    release_version: str
    nodes: list[KnowledgeGraphNodeResponse]
    edges: list[KnowledgeGraphEdgeResponse]
    paths: list[KnowledgeGraphPathResponse]
    evidence: list[KnowledgeGraphEvidenceResponse]
    partial: bool
    backend: Literal["mysql", "neo4j"]
