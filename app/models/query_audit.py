"""ORM model for request-level query audit records."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class QueryAuditMySQL(Base):
    """Persisted audit row for one `/api/query` execution."""

    __tablename__ = "query_audit"
    __table_args__ = (
        Index("idx_query_audit_user_created", "user_id", "created_at"),
        Index("idx_query_audit_policy_created", "policy_version", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    policy_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allowed_department_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    authz_outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    route_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metric_query: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cube_query: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sql: Mapped[str | None] = mapped_column("sql_text", Text, nullable=True)
    normalized_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_policy_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sql_rejection_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sql_estimated_rows: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sql_query_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    result_truncated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sql_execution_duration_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    llm_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_call_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    llm_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_cost_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_release_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
