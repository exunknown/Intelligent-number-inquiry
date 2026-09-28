"""Metric governance candidate service."""

from app.entities.metric_candidate import MetricCandidate
from app.repositories.mysql.meta.metric_candidate_repository import (
    MetricCandidateRepository,
)


class MetricCandidateService:
    """Expose read-only candidate listing to the API layer."""

    def __init__(self, repository: MetricCandidateRepository):
        self.repository = repository

    async def list_candidates(self, status: str, limit: int) -> list[MetricCandidate]:
        return await self.repository.list_candidates(status=status, limit=limit)

    async def review_candidate(
        self, candidate_id: str, status: str, review_note: str | None
    ) -> MetricCandidate | None:
        return await self.repository.review(
            candidate_id=candidate_id, status=status, review_note=review_note
        )
