"""语义层成员 ORM 模型。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class SemanticMemberMySQL(Base):
    """保存一个发布版本中的指标或维度公共属性。"""

    __tablename__ = "semantic_member"
    __table_args__ = (
        Index("idx_semantic_member_release_type", "release_version", "member_type"),
        Index("idx_semantic_member_release_status", "release_version", "status"),
    )

    release_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    member_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    cube_name: Mapped[str] = mapped_column(String(128), nullable=False)
    member_name: Mapped[str] = mapped_column(String(128), nullable=False)
    member_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    data_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_column_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ai_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    aliases_json: Mapped[list] = mapped_column(JSON, nullable=False)
    filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    groupable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
