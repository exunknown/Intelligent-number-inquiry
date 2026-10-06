"""元数据知识图谱的业务实体。"""

from dataclasses import dataclass
from math import isfinite
from typing import Final, TypeAlias

NodeType: TypeAlias = str
EdgeType: TypeAlias = str

TECHNICAL_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "table",
        "column",
        "cube",
        "semantic_member",
        "metric_equivalence_group",
        "business_term",
        "value",
    }
)

BUSINESS_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "customer_segment",
        "customer",
        "product",
        "category",
        "brand",
        "region",
        "metric",
        "time_period",
    }
)

NODE_TYPES: Final[frozenset[str]] = TECHNICAL_NODE_TYPES | BUSINESS_NODE_TYPES

TECHNICAL_EDGE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "TABLE_HAS_COLUMN",
        "COLUMN_BELONGS_TO_TABLE",
        "COLUMN_REFERENCES_COLUMN",
        "CUBE_ON_TABLE",
        "CUBE_JOIN_CUBE",
        "MEMBER_IN_CUBE",
        "MEMBER_SOURCE_COLUMN",
        "MEASURE_DEPENDS_ON_MEMBER",
        "METRIC_EQUIVALENT_TO",
        "METRIC_ATTACHED_TO",
        "TERM_ALIASES_MEMBER",
        "VALUE_BELONGS_TO_COLUMN",
    }
)

BUSINESS_EDGE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "CUSTOMER_IN_SEGMENT",
        "CUSTOMER_PURCHASED_PRODUCT",
        "SEGMENT_PREFERS_CATEGORY",
        "SEGMENT_PREFERS_BRAND",
        "PRODUCT_BELONGS_TO_CATEGORY",
        "PRODUCT_OF_BRAND",
        "PRODUCT_HOT_IN_REGION",
        "CATEGORY_CONTRIBUTES_TO_REGION",
        "PRODUCT_ASSOCIATED_WITH_PRODUCT",
        "METRIC_MEASURES_OBJECT",
        "METRIC_IN_PERIOD",
    }
)

EDGE_TYPES: Final[frozenset[str]] = TECHNICAL_EDGE_TYPES | BUSINESS_EDGE_TYPES

NODE_ID_PREFIXES: Final[dict[str, str]] = {
    "table": "table:",
    "column": "column:",
    "cube": "cube:",
    "semantic_member": "member:",
    "metric_equivalence_group": "equivalence:",
    "business_term": "term:",
    "value": "value:",
    "customer_segment": "segment:",
    "customer": "customer:",
    "product": "product:",
    "category": "category:",
    "brand": "brand:",
    "region": "region:",
    "metric": "metric:",
    "time_period": "period:",
}

SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "authorization",
        "connection",
        "connection_string",
        "database_url",
        "dsn",
        "executable_sql",
        "full_result",
        "normalized_sql",
        "password",
        "prompt",
        "raw_sql",
        "raw_result",
        "records",
        "result",
        "result_rows",
        "rows",
        "secret",
        "sql",
        "token",
    }
)


def _safe_value(value: object) -> object:
    """递归移除图谱实体中不允许持久化和展示的字段。"""

    if isinstance(value, dict):
        return {
            str(key): _safe_value(item)
            for key, item in value.items()
            if str(key).strip().lower() not in SENSITIVE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def _validate_score(name: str, value: float, *, allow_zero: bool = False) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    if not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
    if allow_zero:
        valid = value >= 0
    else:
        valid = value > 0
    if not valid:
        comparator = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be {comparator}")


@dataclass(frozen=True)
class KnowledgeGraphNode:
    """一个绑定元数据发布版本的图谱节点。"""

    node_id: str
    node_type: NodeType
    title: str
    description: str
    payload: dict[str, object]
    source: str
    confidence: float
    release_version: str

    def __post_init__(self) -> None:
        if self.node_type not in NODE_TYPES:
            raise ValueError(f"unsupported node_type: {self.node_type}")
        prefix = NODE_ID_PREFIXES[self.node_type]
        if not self.node_id.startswith(prefix):
            raise ValueError(f"node_id for {self.node_type} must start with {prefix}")
        if not self.release_version.strip():
            raise ValueError("release_version must not be empty")
        _validate_score("confidence", self.confidence)

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "title": self.title,
            "description": self.description,
            "payload": _safe_value(self.payload),
            "source": self.source,
            "confidence": self.confidence,
            "release_version": self.release_version,
        }


@dataclass(frozen=True)
class KnowledgeGraphEdge:
    """一个绑定元数据发布版本的有向图谱边。"""

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType
    weight: float
    evidence: dict[str, object]
    source: str
    release_version: str

    def __post_init__(self) -> None:
        if self.edge_type not in EDGE_TYPES:
            raise ValueError(f"unsupported edge_type: {self.edge_type}")
        if not self.source_node_id or not self.target_node_id:
            raise ValueError("edge endpoints must not be empty")
        if not self.release_version.strip():
            raise ValueError("release_version must not be empty")
        _validate_score("weight", self.weight)

    def to_dict(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "edge_type": self.edge_type,
            "weight": self.weight,
            "evidence": _safe_value(self.evidence),
            "source": self.source,
            "release_version": self.release_version,
        }


@dataclass(frozen=True)
class KnowledgeGraphPath:
    """图谱召回返回的一条有向路径。"""

    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    score: float

    def __post_init__(self) -> None:
        if not self.node_ids or len(self.edge_ids) != len(self.node_ids) - 1:
            raise ValueError("path node and edge counts are inconsistent")
        _validate_score("score", self.score, allow_zero=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "score": self.score,
        }
