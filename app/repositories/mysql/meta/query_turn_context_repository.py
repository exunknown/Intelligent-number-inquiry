"""查询轮次上下文仓储。"""

import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.query_turn_context import QueryTurnContext
from app.models.query_turn_context import QueryTurnContextMySQL


class QueryTurnContextRepository:
    """按用户和会话读取、幂等保存成功查询上下文。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _to_entity(model: QueryTurnContextMySQL) -> QueryTurnContext:
        return QueryTurnContext(
            context_id=model.id,
            session_id=model.session_id,
            user_id=model.user_id,
            request_id=model.request_id,
            user_message_sequence_no=model.user_message_sequence_no,
            effective_query=model.effective_query,
            query_mode=model.query_mode,
            context=model.context_json,
            result_summary=model.result_summary_json,
            metadata_release_version=model.metadata_release_version,
            inherited_from_context_id=model.inherited_from_context_id,
            context_schema_version=model.context_schema_version,
            created_at=model.created_at,
        )

    @staticmethod
    def _payload(context: QueryTurnContext) -> dict[str, object]:
        return {
            "effective_query": context.effective_query,
            "query_mode": context.query_mode,
            "context": context.context,
            "result_summary": context.result_summary,
            "metadata_release_version": context.metadata_release_version,
            "created_at": context.created_at.isoformat(),
        }

    @classmethod
    def _serialized_length(cls, contexts: list[QueryTurnContext]) -> int:
        return len(
            "\n".join(
                json.dumps(
                    cls._payload(context),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                for context in contexts
            )
        )

    @staticmethod
    def _is_duplicate_request_error(error: IntegrityError) -> bool:
        original = error.orig
        values = [str(original), str(error)]
        args = getattr(original, "args", ())
        values.extend(str(value) for value in args)
        message = " ".join(values).lower()
        return (
            "1062" in message and ("duplicate" in message or "unique" in message)
        ) or (
            "duplicate" in message
            and ("request_id" in message or "uq_query_turn_context_request" in message)
        )

    async def list_recent_successful(
        self,
        session_id: str,
        user_id: str,
        limit: int,
        max_context_chars: int,
    ) -> list[QueryTurnContext]:
        """读取当前用户会话中最近且能放入预算的成功上下文。"""

        if limit <= 0 or max_context_chars <= 0:
            return []

        result = await self.session.execute(
            select(QueryTurnContextMySQL)
            .where(
                QueryTurnContextMySQL.session_id == session_id,
                QueryTurnContextMySQL.user_id == user_id,
            )
            .order_by(
                QueryTurnContextMySQL.created_at.desc(),
                QueryTurnContextMySQL.id.desc(),
            )
            .limit(limit)
        )
        recent = [self._to_entity(model) for model in result.scalars().all()]

        selected: list[QueryTurnContext] = []
        for context in recent:
            candidate = [*selected, context]
            if self._serialized_length(candidate) > max_context_chars:
                break
            selected.append(context)
        return list(reversed(selected))

    async def save_if_absent(
        self, context: QueryTurnContext
    ) -> QueryTurnContext | None:
        """按 request_id 幂等保存上下文，重复写入返回 None。"""

        model = QueryTurnContextMySQL(
            id=context.context_id,
            session_id=context.session_id,
            user_id=context.user_id,
            request_id=context.request_id,
            user_message_sequence_no=context.user_message_sequence_no,
            effective_query=context.effective_query,
            query_mode=context.query_mode,
            context_json=context.context,
            result_summary_json=context.result_summary,
            metadata_release_version=context.metadata_release_version,
            inherited_from_context_id=context.inherited_from_context_id,
            context_schema_version=context.context_schema_version,
            created_at=context.created_at,
        )
        self.session.add(model)
        try:
            await self.session.commit()
        except IntegrityError as error:
            await self.session.rollback()
            if self._is_duplicate_request_error(error):
                return None
            raise
        except Exception:
            await self.session.rollback()
            raise
        return context
