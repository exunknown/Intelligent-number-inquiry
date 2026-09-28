"""Metric governance candidates produced by the Text-to-SQL fallback."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MetricCandidate:
    """A normalized question waiting for metric governance review."""

    id: str
    query_text: str
    route_reason: str | None
    source_request_id: str | None
    status: str
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    reviewed_at: datetime | None
    review_note: str | None
