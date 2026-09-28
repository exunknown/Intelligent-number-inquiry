"""ORM model for Text-to-SQL governance candidates."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetricCandidateMySQL(Base):
    """Persisted candidate question for later metric modeling."""

    __tablename__ = "metric_candidate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    route_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
