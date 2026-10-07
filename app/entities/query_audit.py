"""Query audit records written after each question execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryAuditRecord:
    """Request-level audit data independent from the persistence model."""

    user_id: str
    username: str | None
    roles: tuple[str, ...]
    policy_version: int
    allowed_department_ids: tuple[str, ...]
    authz_outcome: str
    query_text: str
    query_mode: str | None
    route_reason: str | None
    metric_query: dict | None
    cube_query: dict | None
    sql: str | None
    outcome: str
    error_code: str | None
    verified: bool | None
    duration_ms: int
    normalized_sql: str | None = None
    executed_sql: str | None = None
    sql_policy_outcome: str | None = None
    sql_rejection_reason: str | None = None
    sql_estimated_rows: int | None = None
    sql_query_cost: float | None = None
    result_row_count: int | None = None
    result_bytes: int | None = None
    result_truncated: bool | None = None
    sql_execution_duration_ms: int | None = None
    llm_call_count: int = 0
    embedding_call_count: int = 0
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None
    llm_cost_units: float | None = None
    metadata_release_version: str | None = None
    business_graph_snapshot_version: str | None = None
    session_id: str | None = None
