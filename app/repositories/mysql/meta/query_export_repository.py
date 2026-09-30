"""MinIO 导出对象归属元数据仓储。"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.query_export import QueryExport
from app.models.query_export import QueryExportMySQL


class QueryExportRepository:
    """只在 Meta MySQL 保存对象归属和过期信息，不保存结果正文。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(model: QueryExportMySQL) -> QueryExport:
        return QueryExport(
            export_id=model.id,
            request_id=model.request_id,
            user_id=model.user_id,
            policy_version=model.policy_version,
            session_id=model.session_id,
            object_key=model.object_key,
            content_type=model.content_type,
            result_bytes=model.result_bytes,
            row_count=model.row_count,
            created_at=model.created_at,
            expires_at=model.expires_at,
        )

    async def create(
        self,
        *,
        export_id: str,
        request_id: str,
        user_id: str,
        policy_version: int,
        session_id: str | None,
        object_key: str,
        result_bytes: int,
        row_count: int | None,
        expires_at: datetime,
    ) -> QueryExport:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        model = QueryExportMySQL(
            id=export_id,
            request_id=request_id,
            user_id=user_id,
            policy_version=policy_version,
            session_id=session_id,
            object_key=object_key,
            result_bytes=result_bytes,
            row_count=row_count,
            created_at=now,
            expires_at=expires_at,
        )
        try:
            self.session.add(model)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return self._to_entity(model)

    async def get_owned(self, export_id: str, user_id: str) -> QueryExport | None:
        result = await self.session.execute(
            select(QueryExportMySQL).where(
                QueryExportMySQL.id == export_id,
                QueryExportMySQL.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model is not None else None
