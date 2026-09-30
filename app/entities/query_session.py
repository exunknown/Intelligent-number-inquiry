"""查询会话领域对象。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class QuerySession:
    """一个用户可见的查询会话摘要。"""

    session_id: str
    user_id: str
    username: str | None
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_request_id: str | None
    last_outcome: str | None
    last_query_mode: str | None
    last_error_code: str | None
    last_metadata_release_version: str | None


@dataclass(frozen=True)
class QuerySessionMessage:
    """历史查询中允许返回给调用者的脱敏摘要。"""

    request_id: str | None
    created_at: datetime
    query_text: str
    outcome: str
    query_mode: str | None
    route_reason: str | None
    verified: bool | None
    error_code: str | None
    duration_ms: int
    metadata_release_version: str | None
    result_row_count: int | None
    result_bytes: int | None
    result_truncated: bool | None
