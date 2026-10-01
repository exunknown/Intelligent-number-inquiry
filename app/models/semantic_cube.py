"""语义层 Cube ORM 模型。"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SemanticCubeMySQL(Base):
    """保存一个发布版本中的 Cube 定义。"""

    __tablename__ = "semantic_cube"
    __table_args__ = ()

    release_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    cube_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    sql_table: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
