"""查询会话消息 ORM 模型。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.entities.metric_display import MetricDisplayItem
from app.models.base import Base


class QueryMessageMySQL(Base):
    """Persisted user-owned message and safe assistant display snapshot."""

    __tablename__ = "query_message"
    __table_args__ = (
        Index(
            "uq_query_message_session_sequence",
            "session_id",
            "sequence_no",
            unique=True,
        ),
        Index("idx_query_message_session_created", "session_id", "created_at"),
        Index("idx_query_message_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    steps_json: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    process_events_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
    metrics_json: Mapped[list[MetricDisplayItem] | None] = mapped_column(
        JSON, nullable=True
    )
    query_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    route_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_preview_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    export_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
