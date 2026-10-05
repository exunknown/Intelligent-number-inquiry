"""查询会话消息接口模型。"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MetricDisplayEntryResponse(BaseModel):
    """Strict public shape for structured metrics; unknown fields are discarded."""

    model_config = ConfigDict(extra="ignore")

    member_id: str
    title: str
    role: Literal["primary", "attached"] | None = None
    source_member_id: str | None = None
    compatibility_note: str | None = None


class MissingRequirementResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["metric", "dimension", "time_range", "field", "data_scope"]
    label: str
    example: str


class ProcessEventResponse(BaseModel):
    """Strict public shape for persisted query process events."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    step: str
    status: Literal["running", "success", "error"]
    message: str | None = None
    occurred_at: datetime


MetricDisplayItemResponse = Annotated[
    str | MetricDisplayEntryResponse,
    Field(union_mode="left_to_right"),
]


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
    metrics: list[MetricDisplayItemResponse] | None
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
    missing_requirements: list[MissingRequirementResponse] | None = None
    process_events: list[ProcessEventResponse] | None = None
    created_at: datetime
