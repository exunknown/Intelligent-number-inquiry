"""查询结果导出对象领域对象。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class QueryExport:
    """一个受用户归属和过期时间保护的 MinIO 结果对象。"""

    export_id: str
    request_id: str
    user_id: str
    policy_version: int
    session_id: str | None
    object_key: str
    content_type: str
    result_bytes: int
    row_count: int | None
    created_at: datetime
    expires_at: datetime
