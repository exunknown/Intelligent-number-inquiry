"""应用侧用户变更审计 ORM 模型。"""

from datetime import datetime

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class AppUserChangeMySQL(Base):
    """应用侧用户状态和角色变更审计记录。"""

    __tablename__ = "app_user_change"
    __table_args__ = (
        Index("idx_app_user_change_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
