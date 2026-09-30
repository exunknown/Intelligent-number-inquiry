"""查询会话 ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QuerySessionMySQL(Base):
    """Persisted user-owned query session metadata."""

    __tablename__ = "query_session"
    __table_args__ = (
        Index("idx_query_session_user_updated", "user_id", "updated_at"),
        Index(
            "idx_query_session_user_state_updated",
            "user_id",
            "archived_at",
            "deleted_at",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_query_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_metadata_release_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
