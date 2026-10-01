"""语义层指标扩展 ORM 模型。"""

from sqlalchemy import ForeignKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class SemanticMeasureDefinitionMySQL(Base):
    """保存指标的受限计算定义。"""

    __tablename__ = "semantic_measure_definition"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_version", "member_id"],
            ["semantic_member.release_version", "semantic_member.member_id"],
        ),
    )

    release_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    member_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    aggregation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dependency_members_json: Mapped[list] = mapped_column(JSON, nullable=False)
