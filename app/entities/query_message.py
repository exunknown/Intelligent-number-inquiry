"""查询会话消息领域对象。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from app.entities.metric_display import MetricDisplayItem

_MISSING_REQUIREMENT_TYPES = frozenset(
    {"metric", "dimension", "time_range", "field", "data_scope"}
)


@dataclass(frozen=True)
class QueryProcessEvent:
    """查询过程允许持久化的单个步骤事件。"""

    step: str
    status: Literal["running", "success", "error"]
    message: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class QueryMissingRequirement:
    """查询失败时允许恢复给用户的缺失条件。"""

    type: str
    label: str
    example: str


def safe_query_missing_requirements(value: object) -> list[QueryMissingRequirement]:
    """只保留公开缺失条件的固定字段和有限长度。"""

    if not isinstance(value, list):
        return []
    requirements: list[QueryMissingRequirement] = []
    seen_types: set[str] = set()
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        requirement_type = item.get("type")
        label = item.get("label")
        example = item.get("example")
        if (
            not isinstance(requirement_type, str)
            or requirement_type not in _MISSING_REQUIREMENT_TYPES
            or requirement_type in seen_types
            or not isinstance(label, str)
            or not label
            or not isinstance(example, str)
            or not example
        ):
            continue
        seen_types.add(requirement_type)
        requirements.append(
            QueryMissingRequirement(
                type=requirement_type,
                label=label[:128],
                example=example[:128],
            )
        )
    return requirements


@dataclass(frozen=True)
class QueryMessageSnapshot:
    """助手消息允许持久化的前端展示快照。"""

    status: str
    content: str
    steps: dict[str, str] = field(default_factory=dict)
    process_events: list[QueryProcessEvent] = field(default_factory=list)
    missing_requirements: list[QueryMissingRequirement] = field(default_factory=list)
    metrics: list[MetricDisplayItem] = field(default_factory=list)
    query_mode: str | None = None
    route_reason: str | None = None
    result_preview: Any = None
    verified: bool | None = None
    warning: str | None = None
    row_count: int | None = None
    truncated: bool | None = None
    export_id: str | None = None
    error: str | None = None
    error_code: str | None = None
    retryable: bool | None = None


@dataclass(frozen=True)
class QueryMessage:
    """一个用户拥有的可恢复会话消息。"""

    message_id: str
    session_id: str
    user_id: str
    request_id: str | None
    sequence_no: int
    role: str
    content: str
    status: str
    steps: dict[str, str] | None
    metrics: list[MetricDisplayItem] | None
    query_mode: str | None
    route_reason: str | None
    result_preview: Any
    verified: bool | None
    warning: str | None
    row_count: int | None
    truncated: bool | None
    export_id: str | None
    error: str | None
    error_code: str | None
    retryable: bool | None
    created_at: datetime
    process_events: list[QueryProcessEvent] | None = None
    missing_requirements: list[QueryMissingRequirement] | None = None
