"""查询会话消息接口模型。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class QueryMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    request_id: str | None
    sequence_no: int
    role: str
    content: str
    status: str
    steps: dict[str, str] | None
    metrics: list[str] | None
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
