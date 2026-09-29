"""元数据发布注册表 ORM 模型。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class MetadataReleaseMySQL(Base):
    """保存不可变 manifest 及其发布状态。"""

    __tablename__ = "metadata_release"
    __table_args__ = (Index("idx_metadata_release_active", "active", "activated_at"),)

    release_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MetadataReleaseLockMySQL(Base):
    """单行数据库锁，串行化发布和回滚。"""

    __tablename__ = "metadata_release_lock"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
