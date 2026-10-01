"""语义模型草稿和操作审计 ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class SemanticModelDraftMySQL(Base):
    """保存可编辑的完整语义模型快照。"""

    __tablename__ = "semantic_model_draft"
    __table_args__ = (Index("idx_semantic_draft_status", "status", "updated_at"),)

    draft_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    release_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SemanticModelChangeMySQL(Base):
    """保存草稿状态变更和幂等键。"""

    __tablename__ = "semantic_model_change"
    __table_args__ = (Index("idx_semantic_change_draft", "draft_id", "created_at"),)

    change_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
