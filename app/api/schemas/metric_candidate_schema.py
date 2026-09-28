"""Metric governance candidate API response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CandidateStatus = Literal["pending", "approved", "rejected"]


class MetricCandidateItem(BaseModel):
    """One candidate question exposed to governance tooling."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    query_text: str
    route_reason: str | None
    source_request_id: str | None
    status: CandidateStatus
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    reviewed_at: datetime | None
    review_note: str | None


class MetricCandidateResponse(BaseModel):
    """Candidate list response."""

    items: list[MetricCandidateItem]
    total: int


class MetricCandidateReviewRequest(BaseModel):
    """Review decision submitted by a governance operator."""

    status: Literal["approved", "rejected"]
    review_note: str | None = Field(default=None, max_length=2000)
