"""Persistence repository for metric governance candidates."""

from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import request_id_ctx_var
from app.entities.metric_candidate import MetricCandidate
from app.models.metric_candidate import MetricCandidateMySQL


def normalize_query(value: str) -> str:
    """Collapse whitespace and normalize case for governance deduplication."""

    return " ".join(value.split()).casefold()


def query_hash(value: str) -> str:
    """Return a stable digest for a normalized natural-language question."""

    return sha256(normalize_query(value).encode("utf-8")).hexdigest()


class MetricCandidateRepository:
    """Upsert and list candidates in the Meta MySQL database."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_pending(self, query_text: str, route_reason: str | None) -> None:
        """Record one SQL fallback without reopening an already reviewed candidate."""

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        model = MetricCandidateMySQL(
            id=str(uuid4()),
            query_hash=query_hash(query_text),
            query_text=query_text,
            route_reason=route_reason,
            source_request_id=str(request_id_ctx_var.get()),
            status="pending",
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        statement = mysql_insert(MetricCandidateMySQL).values(
            {
                column.name: getattr(model, column.name)
                for column in MetricCandidateMySQL.__table__.columns
            }
        )
        statement = statement.on_duplicate_key_update(
            query_text=statement.inserted.query_text,
            route_reason=statement.inserted.route_reason,
            source_request_id=statement.inserted.source_request_id,
            occurrence_count=MetricCandidateMySQL.occurrence_count + 1,
            last_seen_at=statement.inserted.last_seen_at,
        )
        try:
            await self.session.execute(statement)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def list_candidates(self, status: str, limit: int) -> list[MetricCandidate]:
        """Return recent candidates filtered by governance status."""

        statement = (
            select(MetricCandidateMySQL)
            .where(MetricCandidateMySQL.status == status)
            .order_by(MetricCandidateMySQL.last_seen_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return [self._to_entity(model) for model in result.scalars().all()]

    async def review(
        self, candidate_id: str, status: str, review_note: str | None
    ) -> MetricCandidate | None:
        """Update one candidate's governance status and review metadata."""

        model = await self.session.get(MetricCandidateMySQL, candidate_id)
        if model is None:
            return None
        model.status = status
        model.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        model.review_note = review_note.strip() if review_note else None
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: MetricCandidateMySQL) -> MetricCandidate:
        return MetricCandidate(
            id=model.id,
            query_text=model.query_text,
            route_reason=model.route_reason,
            source_request_id=model.source_request_id,
            status=model.status,
            occurrence_count=model.occurrence_count,
            first_seen_at=model.first_seen_at,
            last_seen_at=model.last_seen_at,
            reviewed_at=model.reviewed_at,
            review_note=model.review_note,
        )
