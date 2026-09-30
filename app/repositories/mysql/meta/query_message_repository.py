"""查询会话消息仓储。"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.query_message import QueryMessage, QueryMessageSnapshot
from app.models.query_message import QueryMessageMySQL
from app.models.query_session import QuerySessionMySQL


class QueryMessageRepository:
    """在 Meta MySQL 中维护用户拥有的会话消息。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _to_entity(model: QueryMessageMySQL) -> QueryMessage:
        return QueryMessage(
            message_id=model.id,
            session_id=model.session_id,
            user_id=model.user_id,
            request_id=model.request_id,
            sequence_no=model.sequence_no,
            role=model.role,
            content=model.content,
            status=model.status,
            steps=model.steps_json,
            metrics=model.metrics_json,
            query_mode=model.query_mode,
            route_reason=model.route_reason,
            result_preview=model.result_preview_json,
            verified=model.verified,
            warning=model.warning,
            row_count=model.row_count,
            truncated=model.truncated,
            export_id=model.export_id,
            error=model.error_message,
            error_code=model.error_code,
            retryable=model.retryable,
            created_at=model.created_at,
        )

    async def _get_owned_session(
        self, session_id: str, user_id: str, *, for_update: bool = False
    ) -> QuerySessionMySQL | None:
        statement = select(QuerySessionMySQL).where(
            QuerySessionMySQL.id == session_id,
            QuerySessionMySQL.user_id == user_id,
            QuerySessionMySQL.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def _next_sequence(self, session_id: str, user_id: str) -> int:
        current = await self.session.scalar(
            select(func.max(QueryMessageMySQL.sequence_no)).where(
                QueryMessageMySQL.session_id == session_id,
                QueryMessageMySQL.user_id == user_id,
            )
        )
        return (current or 0) + 1

    async def _append(
        self,
        session_id: str,
        user_id: str,
        request_id: str | None,
        *,
        role: str,
        content: str,
        status: str,
        snapshot: QueryMessageSnapshot | None = None,
        metadata_release_version: str | None = None,
    ) -> QueryMessage | None:
        owned = await self._get_owned_session(session_id, user_id, for_update=True)
        if owned is None or owned.archived_at is not None:
            return None

        sequence_no = await self._next_sequence(session_id, user_id)
        now = self._now()
        model = QueryMessageMySQL(
            id=str(uuid4()),
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            sequence_no=sequence_no,
            role=role,
            content=content,
            status=status,
            steps_json=snapshot.steps if snapshot is not None else None,
            metrics_json=snapshot.metrics if snapshot is not None else None,
            query_mode=snapshot.query_mode if snapshot is not None else None,
            route_reason=snapshot.route_reason if snapshot is not None else None,
            result_preview_json=(
                snapshot.result_preview if snapshot is not None else None
            ),
            verified=snapshot.verified if snapshot is not None else None,
            warning=snapshot.warning if snapshot is not None else None,
            row_count=snapshot.row_count if snapshot is not None else None,
            truncated=snapshot.truncated if snapshot is not None else None,
            export_id=snapshot.export_id if snapshot is not None else None,
            error_message=snapshot.error if snapshot is not None else None,
            error_code=snapshot.error_code if snapshot is not None else None,
            retryable=snapshot.retryable if snapshot is not None else None,
            created_at=now,
        )
        self.session.add(model)
        owned.message_count += 1
        owned.updated_at = now
        if snapshot is not None:
            owned.last_request_id = request_id
            owned.last_outcome = (
                "error"
                if snapshot.status == "error"
                else "success"
                if snapshot.status == "done"
                else snapshot.status
            )
            owned.last_query_mode = snapshot.query_mode
            owned.last_error_code = snapshot.error_code
        if metadata_release_version is not None:
            owned.last_metadata_release_version = metadata_release_version
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._to_entity(model)

    async def append_user_message(
        self, session_id: str, user_id: str, request_id: str, content: str
    ) -> QueryMessage | None:
        return await self._append(
            session_id,
            user_id,
            request_id,
            role="user",
            content=content,
            status="done",
        )

    async def append_assistant_message(
        self,
        session_id: str,
        user_id: str,
        request_id: str,
        snapshot: QueryMessageSnapshot,
        *,
        metadata_release_version: str | None = None,
    ) -> QueryMessage | None:
        return await self._append(
            session_id,
            user_id,
            request_id,
            role="assistant",
            content=snapshot.content,
            status=snapshot.status,
            snapshot=snapshot,
            metadata_release_version=metadata_release_version,
        )

    async def list_owned_messages(
        self, session_id: str, user_id: str, limit: int = 100, offset: int = 0
    ) -> list[QueryMessage] | None:
        owned = await self._get_owned_session(session_id, user_id)
        if owned is None:
            return None
        result = await self.session.execute(
            select(QueryMessageMySQL)
            .where(
                QueryMessageMySQL.session_id == session_id,
                QueryMessageMySQL.user_id == user_id,
            )
            .order_by(
                QueryMessageMySQL.sequence_no.asc(),
                QueryMessageMySQL.created_at.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return [self._to_entity(model) for model in result.scalars().all()]
