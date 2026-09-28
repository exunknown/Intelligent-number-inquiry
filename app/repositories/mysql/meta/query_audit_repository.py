"""Persistence repository for query audit rows."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import request_id_ctx_var
from app.entities.query_audit import QueryAuditRecord
from app.models.query_audit import QueryAuditMySQL


class QueryAuditRepository:
    """Save one completed query audit record in Meta MySQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, record: QueryAuditRecord) -> None:
        model = QueryAuditMySQL(
            id=str(uuid4()),
            request_id=request_id_ctx_var.get(),
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            query_text=record.query_text,
            query_mode=record.query_mode,
            route_reason=record.route_reason,
            metric_query=record.metric_query,
            cube_query=record.cube_query,
            sql=record.sql,
            outcome=record.outcome,
            error_code=record.error_code,
            verified=record.verified,
            duration_ms=record.duration_ms,
        )
        try:
            self.session.add(model)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
