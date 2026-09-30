"""应用侧用户角色 ORM 模型。"""

from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppUserRoleMySQL(Base):
    """应用侧角色的可重放历史记录。"""

    __tablename__ = "app_user_role"
    __table_args__ = (
        Index(
            "idx_app_user_role_user_role_revoked",
            "user_id",
            "role_code",
            "revoked_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
