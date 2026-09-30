"""应用侧用户 ORM 模型。"""

from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class AppUserMySQL(Base):
    """Meta MySQL 中的应用侧用户快照。"""

    __tablename__ = "app_user"
    __table_args__ = (
        Index("idx_app_user_status_last_seen", "status", "last_seen_at"),
        Index("idx_app_user_username", "username"),
    )

    user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_roles_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    disabled_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
