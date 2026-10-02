"""查询会话消息领域对象。"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.entities.metric_display import MetricDisplayItem


@dataclass(frozen=True)
class QueryMessageSnapshot:
    """助手消息允许持久化的前端展示快照。"""

    status: str
    content: str
    steps: dict[str, str] = field(default_factory=dict)
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
