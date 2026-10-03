"""查询轮次上下文领域对象。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class QueryTurnContext:
    """一轮成功查询可供后续追问使用的结构化上下文。"""

    context_id: str
    session_id: str
    user_id: str
    request_id: str
    user_message_sequence_no: int
    effective_query: str
    query_mode: str
    context: dict[str, object]
    result_summary: dict[str, object] | None
    metadata_release_version: str | None
    inherited_from_context_id: str | None
    context_schema_version: int
    created_at: datetime
