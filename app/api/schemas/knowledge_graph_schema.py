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
]


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
