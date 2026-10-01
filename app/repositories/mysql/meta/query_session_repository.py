"""查询会话及历史摘要仓储。"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import request_id_ctx_var
from app.entities.query_session import QuerySession, QuerySessionMessage
from app.models.query_audit import QueryAuditMySQL
from app.models.query_session import QuerySessionMySQL


class QuerySessionRepository:
    """在 Meta MySQL 中维护用户拥有的会话索引和审计摘要。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _to_session(model: QuerySessionMySQL) -> QuerySession:
        return QuerySession(
            session_id=model.id,
            user_id=model.user_id,
            username=model.username,
            title=model.title,
            created_at=model.created_at,
            updated_at=model.updated_at,
            message_count=model.message_count,
            last_request_id=model.last_request_id,
            last_outcome=model.last_outcome,
            last_query_mode=model.last_query_mode,
            last_error_code=model.last_error_code,
            last_metadata_release_version=model.last_metadata_release_version,
            archived_at=model.archived_at,
            deleted_at=model.deleted_at,
        )

    async def create(
        self, user_id: str, username: str | None, title: str | None
    ) -> QuerySession:
        now = self._now()
        clean_title = " ".join((title or "新查询会话").split())[:200] or "新查询会话"
        model = QuerySessionMySQL(
            id=str(uuid4()),
            user_id=user_id,
            username=username,
            title=clean_title,
            created_at=now,
            updated_at=now,
            message_count=0,
        )
        try:
            self.session.add(model)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._to_session(model)

    async def get_owned(self, session_id: str, user_id: str) -> QuerySession | None:
        result = await self.session.execute(
            select(QuerySessionMySQL).where(
                QuerySessionMySQL.id == session_id,
                QuerySessionMySQL.user_id == user_id,
                QuerySessionMySQL.deleted_at.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        return self._to_session(model) if model is not None else None

    async def list_owned(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> list[QuerySession]:
        filters = [
            QuerySessionMySQL.user_id == user_id,
            QuerySessionMySQL.deleted_at.is_(None),
        ]
        if not include_archived:
            filters.append(QuerySessionMySQL.archived_at.is_(None))
        result = await self.session.execute(
            select(QuerySessionMySQL)
            .where(*filters)
            .order_by(
                QuerySessionMySQL.updated_at.desc(),
                QuerySessionMySQL.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return [self._to_session(model) for model in result.scalars().all()]

    @staticmethod
    def _owned_filters(
        user_id: str,
        include_archived: bool = False,
    ) -> list:
        filters = [
            QuerySessionMySQL.user_id == user_id,
            QuerySessionMySQL.deleted_at.is_(None),
        ]
        if not include_archived:
            filters.append(QuerySessionMySQL.archived_at.is_(None))
        return filters

    async def search_owned(
        self,
        user_id: str,
        query: str | None = None,
        limit: int = 10,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[list[QuerySession], int]:
        clean_query = " ".join((query or "").split())[:200]
        filters = self._owned_filters(user_id, include_archived)
        if clean_query:
            filters.append(QuerySessionMySQL.title.ilike(f"%{clean_query}%"))

        total = await self.session.scalar(
            select(func.count()).select_from(QuerySessionMySQL).where(*filters)
        )
        result = await self.session.execute(
            select(QuerySessionMySQL)
            .where(*filters)
            .order_by(
                QuerySessionMySQL.updated_at.desc(),
                QuerySessionMySQL.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        sessions = [self._to_session(model) for model in result.scalars().all()]
        return sessions, total

    @staticmethod
    def _normalize_title(title: str) -> str:
        return " ".join(title.split())[:200]

    async def update_title(
        self, session_id: str, user_id: str, title: str
    ) -> QuerySession | None:
        clean_title = self._normalize_title(title)
        if not clean_title:
            raise ValueError("session title must not be blank")
        model = await self.session.scalar(
            select(QuerySessionMySQL).where(
                QuerySessionMySQL.id == session_id,
                QuerySessionMySQL.user_id == user_id,
                QuerySessionMySQL.deleted_at.is_(None),
            )
        )
        if model is None:
            return None
        model.title = clean_title
        model.updated_at = self._now()
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._to_session(model)

    async def set_archived(
        self, session_id: str, user_id: str, archived: bool
    ) -> QuerySession | None:
        model = await self.session.scalar(
            select(QuerySessionMySQL).where(
                QuerySessionMySQL.id == session_id,
                QuerySessionMySQL.user_id == user_id,
                QuerySessionMySQL.deleted_at.is_(None),
            )
        )
        if model is None:
            return None
        model.archived_at = self._now() if archived else None
        model.updated_at = self._now()
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._to_session(model)

    async def soft_delete(self, session_id: str, user_id: str) -> bool:
        model = await self.session.scalar(
            select(QuerySessionMySQL).where(
                QuerySessionMySQL.id == session_id,
                QuerySessionMySQL.user_id == user_id,
                QuerySessionMySQL.deleted_at.is_(None),
            )
        )
        if model is None:
            return False
        model.deleted_at = self._now()
        model.updated_at = self._now()
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return True

    async def touch(
        self,
        session_id: str,
        user_id: str,
        *,
        outcome: str,
        query_mode: str | None,
        error_code: str | None,
        metadata_release_version: str | None,
    ) -> None:
        model = await self.session.scalar(
            select(QuerySessionMySQL).where(
                QuerySessionMySQL.id == session_id,
                QuerySessionMySQL.user_id == user_id,
            )
        )
        if model is None:
            return
        model.message_count += 1
        model.updated_at = self._now()
        model.last_request_id = str(request_id_ctx_var.get())
        model.last_outcome = outcome
        model.last_query_mode = query_mode
        model.last_error_code = error_code
        model.last_metadata_release_version = metadata_release_version
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def list_messages(
        self, session_id: str, user_id: str, limit: int = 100, offset: int = 0
    ) -> list[QuerySessionMessage] | None:
        owned = await self.get_owned(session_id, user_id)
        if owned is None:
            return None
        result = await self.session.execute(
            select(QueryAuditMySQL)
            .where(
                QueryAuditMySQL.session_id == session_id,
                QueryAuditMySQL.user_id == user_id,
            )
            .order_by(QueryAuditMySQL.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return [
            QuerySessionMessage(
                request_id=model.request_id,
                created_at=model.created_at,
                query_text=model.query_text,
                outcome=model.outcome,
                query_mode=model.query_mode,
                route_reason=model.route_reason,
                verified=model.verified,
                error_code=model.error_code,
                duration_ms=model.duration_ms,
                metadata_release_version=model.metadata_release_version,
                result_row_count=model.result_row_count,
                result_bytes=model.result_bytes,
                result_truncated=model.result_truncated,
            )
            for model in result.scalars().all()
        ]
