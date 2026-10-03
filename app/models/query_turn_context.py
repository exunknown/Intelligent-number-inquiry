"""查询轮次上下文 ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.mysql import INTEGER, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class QueryTurnContextMySQL(Base):
    """保存当前用户会话中成功查询的结构化上下文。"""

    __tablename__ = "query_turn_context"
    __table_args__ = (
        Index(
            "uq_query_turn_context_request",
            "request_id",
            unique=True,
        ),
        Index(
            "idx_query_turn_context_session_created",
            "session_id",
            "created_at",
            "id",
        ),
        Index(
            "idx_query_turn_context_user_session_created",
            "user_id",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_message_sequence_no: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False
    )
    effective_query: Mapped[str] = mapped_column(Text, nullable=False)
    query_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    context_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    result_summary_json: Mapped[dict[str, object] | None] = mapped_column(
        JSON, nullable=True
    )
    metadata_release_version: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    inherited_from_context_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    context_schema_version: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True), nullable=False, default=1
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
