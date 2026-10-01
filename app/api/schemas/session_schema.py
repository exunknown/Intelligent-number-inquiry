"""查询会话接口模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.query_message_schema import QueryMessageResponse


class QuerySessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class QuerySessionUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class QuerySessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_request_id: str | None
    last_outcome: str | None
    last_query_mode: str | None
    last_error_code: str | None
    last_metadata_release_version: str | None
    archived_at: datetime | None = None


class QuerySessionPage(BaseModel):
    items: list[QuerySessionSummary]
    total: int
    limit: int
    offset: int


class QuerySessionMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class QuerySessionDetail(BaseModel):
    session: QuerySessionSummary
    messages: list[QueryMessageResponse | QuerySessionMessageResponse]
