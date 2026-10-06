"""元数据知识图谱 ORM 模型。"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base


class KnowledgeGraphNodeMySQL(Base):
    """保存一个元数据发布版本中的图谱节点。"""

    __tablename__ = "knowledge_graph_node"
    __table_args__ = (
        Index("idx_knowledge_graph_node_release_type", "release_version", "node_type"),
    )

    release_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    node_id: Mapped[str] = mapped_column(String(192), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class KnowledgeGraphEdgeMySQL(Base):
    """保存一个元数据发布版本中的图谱有向边。"""

    __tablename__ = "knowledge_graph_edge"
    __table_args__ = (
        Index(
            "idx_knowledge_graph_edge_release_source",
            "release_version",
            "source_node_id",
        ),
        Index(
            "idx_knowledge_graph_edge_release_target",
            "release_version",
            "target_node_id",
        ),
        Index(
            "idx_knowledge_graph_edge_release_type",
            "release_version",
            "edge_type",
        ),
    )

    release_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    edge_id: Mapped[str] = mapped_column(String(192), primary_key=True)
    source_node_id: Mapped[str] = mapped_column(String(192), nullable=False)
    target_node_id: Mapped[str] = mapped_column(String(192), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
