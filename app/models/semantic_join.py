"""语义层 Cube Join ORM 模型。"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SemanticJoinMySQL(Base):
    """保存一个发布版本中的 Cube Join。"""

    __tablename__ = "semantic_join"
    __table_args__ = ()

    release_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    cube_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    target_cube_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    sql_expression: Mapped[str] = mapped_column(Text, nullable=False)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
