"""查询结果导出对象 ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QueryExportMySQL(Base):
    """Persisted ownership metadata for one MinIO result object."""

    __tablename__ = "query_export"
    __table_args__ = (
        Index("idx_query_export_user_created", "user_id", "created_at"),
        Index("idx_query_export_expires", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    object_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(
        String(128), nullable=False, default="application/json; charset=utf-8"
    )
    result_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
