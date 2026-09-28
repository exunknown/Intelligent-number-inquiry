"""ORM model for request-level query audit records."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class QueryAuditMySQL(Base):
    """Persisted audit row for one `/api/query` execution."""

    __tablename__ = "query_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    route_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metric_query: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cube_query: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sql: Mapped[str | None] = mapped_column("sql_text", Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
