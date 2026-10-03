"""会话上下文安全裁剪和解析结果校验。"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.entities.query_turn_context import QueryTurnContext


@dataclass(frozen=True)
class ConversationResolution:
    """模型对当前问题与历史上下文关系的解析结果。"""

    mode: str
    effective_query: str
    inherited_context_id: str | None
    reason: str


class ConversationContextBuilder:
    """构造可传入模型的最小、确定性且脱敏的会话上下文。"""

    _SENSITIVE_KEYS = frozenset(
        {
            "sql",
            "raw_sql",
            "normalized_sql",
            "executable_sql",
            "prompt",
            "token",
            "secret",
            "password",
            "authorization",
            "connection",
            "connection_info",
            "connection_string",
            "database",
            "database_url",
            "db",
            "db_host",
            "db_url",
            "data",
            "dsn",
            "full_result",
            "host",
            "hostname",
            "items",
            "port",
            "raw_result",
            "records",
            "result",
            "result_rows",
            "rows",
        }
    )
    _ALLOWED_FIELDS = (
        "effective_query",
        "query_mode",
        "context",
        "result_summary",
        "metadata_release_version",
        "created_at",
    )

    @classmethod
    def _normalize_key(cls, key: object) -> str:
        return str(key).strip().lower().replace("-", "_").replace(" ", "_")

    @classmethod
    def _sanitize_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._sanitize_value(item)
                for key, item in value.items()
                if cls._normalize_key(key) not in cls._SENSITIVE_KEYS
            }
        if isinstance(value, list):
            return [cls._sanitize_value(item) for item in value]
        if isinstance(value, tuple):
            return [cls._sanitize_value(item) for item in value]
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    @classmethod
    def _sanitize_result_summary(cls, value: Any) -> dict[str, object] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            return {}
        result: dict[str, object] = {}
        for key, item in value.items():
            normalized_key = cls._normalize_key(key)
            if normalized_key in cls._SENSITIVE_KEYS:
                continue
            sanitized = cls._sanitize_value(item)
            if isinstance(sanitized, (str, int, float, bool)) or sanitized is None:
                result[str(key)] = sanitized
        return result

    @classmethod
    def _payload(cls, context: QueryTurnContext) -> dict[str, object]:
        payload: dict[str, object] = {}
        for field in cls._ALLOWED_FIELDS:
            value = getattr(context, field)
            payload[field] = (
                cls._sanitize_result_summary(value)
                if field == "result_summary"
                else cls._sanitize_value(value)
            )
        return payload

    @classmethod
    def serialize_context(cls, context: QueryTurnContext) -> str:
        return json.dumps(
            cls._payload(context),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def build_prompt_context(
        cls, contexts: list[QueryTurnContext], max_chars: int
    ) -> str:
        """保留最近三轮并按字符预算输出换行分隔的确定性 JSON。"""

        if max_chars <= 0 or not contexts:
            return ""

        candidates = contexts[-3:]
        selected: list[str] = []
        for context in reversed(candidates):
            serialized = cls.serialize_context(context)
            candidate = [serialized, *selected]
            prompt_context = "\n".join(candidate)
            if len(prompt_context) > max_chars:
                continue
            selected.insert(0, serialized)
        return "\n".join(selected)

    @classmethod
    def validate_resolution(
        cls,
        resolution: ConversationResolution,
        contexts: list[QueryTurnContext],
    ) -> ConversationResolution:
        """校验模型解析结果只能继承已加载的上下文。"""

        if resolution.mode not in {"standalone", "follow_up", "clarification"}:
            raise ValueError("unsupported conversation mode")
        if not resolution.effective_query.strip():
            raise ValueError("effective query must not be blank")
        context_ids = {context.context_id for context in contexts}
        if (
            resolution.inherited_context_id is not None
            and resolution.inherited_context_id not in context_ids
        ):
            raise ValueError("inherited context is not available")
        if resolution.mode == "follow_up":
            if resolution.inherited_context_id is None:
                raise ValueError("inherited context is not available")
        return resolution
