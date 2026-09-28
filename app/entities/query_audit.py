"""Query audit records written after each question execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryAuditRecord:
    """Request-level audit data independent from the persistence model."""

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
