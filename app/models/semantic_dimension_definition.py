"""语义层维度扩展 ORM 模型。"""

from sqlalchemy import Boolean, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SemanticDimensionDefinitionMySQL(Base):
    """保存维度和时间维度的特有定义。"""

    __tablename__ = "semantic_dimension_definition"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_version", "member_id"],
            ["semantic_member.release_version", "semantic_member.member_id"],
        ),
    )

    release_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    member_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dimension_type: Mapped[str] = mapped_column(String(32), nullable=False)
    time_granularity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    primary_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
