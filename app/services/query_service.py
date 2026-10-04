"""Question execution service and SSE serialization."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from time import perf_counter
from uuid import uuid4

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.agent import state as agent_state
from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.context import request_id_ctx_var
from app.core.log import logger
from app.core.query_errors import QueryExecutionError
from app.core.query_metrics import QueryMetrics, get_query_metrics
from app.core.resource_governance import (
    AdmissionLease,
    LLMUsageCallbackHandler,
    RequestBudget,
    get_dependency_breakers,
    get_resource_admission,
)
from app.entities.auth import QueryPrincipal
from app.entities.metric_display import MetricDisplayItem, safe_metric_display_items
from app.entities.query_audit import QueryAuditRecord
from app.entities.query_message import QueryMessageSnapshot
from app.entities.query_turn_context import QueryTurnContext
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.minio.result_object_store import ResultObjectStore
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.dw.sql_fallback_repository import SQLFallbackRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.metadata_release_repository import (
    MetadataReleaseRepository,
)
from app.repositories.mysql.meta.metric_candidate_repository import (
    MetricCandidateRepository,
)
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository
from app.repositories.mysql.meta.query_export_repository import QueryExportRepository
from app.repositories.mysql.meta.query_message_repository import QueryMessageRepository
from app.repositories.mysql.meta.query_session_repository import QuerySessionRepository
from app.repositories.mysql.meta.query_turn_context_repository import (
    QueryTurnContextRepository,
)
from app.repositories.mysql.meta.semantic_model_repository import (
    SemanticModelRepository,
)
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.repositories.redis.sse_event_repository import SSEEventRepository
from app.security.sql_policy import SQLPolicyEngine
from app.services.cache_service import CacheService
from app.services.conversation_context import ConversationContextBuilder
from app.services.semantic_metric_relation_service import SemanticMetricRelationService

_AUDIT_EVENT_FIELDS = (
    "query_mode",
    "route_reason",
    "metric_query",
    "cube_query",
    "sql",
    "normalized_sql",
    "executed_sql",
    "sql_policy_outcome",
    "sql_rejection_reason",
    "sql_estimated_rows",
    "sql_query_cost",
    "result_row_count",
    "result_bytes",
    "result_truncated",
    "sql_execution_duration_ms",
    "turn_context",
)
_SSE_PROTOCOL_VERSION = 1
_SEMANTIC_SNAPSHOT_TIMEOUT_SECONDS = 1.0


def build_turn_context_payload(
    state: DataAgentState, result_summary: dict[str, object] | None
) -> dict[str, object]:
    """公开安全轮次上下文构造器，供服务和测试复用。"""

    return agent_state.build_turn_context_payload(state, result_summary)


def _safe_turn_context_event(value: object) -> dict[str, object] | None:
    """只接收内部事件中的安全轮次上下文字段。"""

    if not isinstance(value, dict):
        return None
    effective_query = value.get("effective_query")
    query_mode = value.get("query_mode")
    context = value.get("context")
    if not isinstance(effective_query, str) or not isinstance(query_mode, str):
        return None
    if not isinstance(context, dict):
        context = {}
    safe_context = {
        key: item
        for key, item in ConversationContextBuilder._sanitize_value(context).items()
    }
    result_summary = ConversationContextBuilder._sanitize_result_summary(
        value.get("result_summary")
    )
    metadata_release_version = value.get("metadata_release_version")
    inherited_from_context_id = value.get("inherited_from_context_id")
    return {
        "effective_query": effective_query,
        "query_mode": query_mode,
        "context": safe_context,
        "result_summary": result_summary,
        "metadata_release_version": (
            metadata_release_version
            if isinstance(metadata_release_version, str)
            else None
        ),
        "inherited_from_context_id": (
            inherited_from_context_id
            if isinstance(inherited_from_context_id, str)
            else None
        ),
    }


def _terminal_result_summary(event: dict) -> dict[str, object]:
    """从结果终态提取行数等摘要，绝不保存结果行。"""

    data = event.get("data")
    row_count = event.get("row_count")
    if row_count is None and isinstance(data, list):
        row_count = len(data)
    summary: dict[str, object] = {}
    if isinstance(row_count, int) and not isinstance(row_count, bool):
        summary["row_count"] = row_count
    if isinstance(event.get("truncated"), bool):
        summary["truncated"] = event["truncated"]
    return summary


async def _lookup_user_message_sequence(
    repository: QueryMessageRepository | None,
    session_id: str,
    user_id: str,
    request_id: str,
) -> int | None:
    """兼容仓储提供的可空序列查询，不让上下文写入影响查询完成。"""

    if repository is None:
        return None
    for method_name in (
        "get_user_message_sequence",
        "get_user_message_sequence_no",
        "find_user_message_sequence",
    ):
        method = getattr(repository, method_name, None)
        if not callable(method):
            continue
        try:
            value = await method(session_id, user_id, request_id)
        except Exception:
            logger.warning("Failed to lookup query user message sequence")
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return None
    return None


def build_query_message_snapshot(
    events: list[dict], terminal_event: dict
) -> QueryMessageSnapshot:
    """把允许展示的 SSE 事件转换成安全的会话消息快照。"""

    steps: dict[str, str] = {}
    metrics: list[MetricDisplayItem] = []
    query_mode = None
    route_reason = None

    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type == "progress":
            step = event.get("step")
            status = event.get("status")
            if (
                isinstance(step, str)
                and isinstance(status, str)
                and status in {"running", "success", "error"}
            ):
                steps[step] = status
        elif event_type == "metrics":
            data = event.get("data")
            if isinstance(data, list):
                metrics = safe_metric_display_items(data)
        elif event_type == "route":
            if isinstance(event.get("mode"), str):
                query_mode = event["mode"]
            if isinstance(event.get("reason"), str):
                route_reason = event["reason"]

    event_type = terminal_event.get("type")
    if event_type == "result":
        data = terminal_event.get("data")
        row_count = terminal_event.get("row_count")
        if row_count is None and isinstance(data, list):
            row_count = len(data)
        if isinstance(row_count, bool) or not isinstance(row_count, (int, type(None))):
            row_count = None
        content = (
            f"查询完成，共返回 {row_count} 条结果。"
            if row_count is not None
            else "查询已完成。"
        )
        return QueryMessageSnapshot(
            status="done",
            content=content,
            steps=steps,
            metrics=metrics,
            query_mode=terminal_event.get("source") or query_mode,
            route_reason=route_reason,
            result_preview=data,
            verified=terminal_event.get("verified"),
            warning=terminal_event.get("warning"),
            row_count=row_count,
            truncated=terminal_event.get("truncated"),
            export_id=terminal_event.get("export_id"),
        )
    if event_type == "cancelled":
        return QueryMessageSnapshot(
            status="cancelled",
            content="已停止本次查询。",
            steps=steps,
            metrics=metrics,
            query_mode=query_mode,
            route_reason=route_reason,
        )

    return QueryMessageSnapshot(
        status="error",
        content="这次查询没有成功。",
        steps=steps,
        metrics=metrics,
        query_mode=query_mode,
        route_reason=route_reason,
        error=(
            terminal_event.get("message")
            if isinstance(terminal_event.get("message"), str)
            else None
        ),
        error_code=(
            terminal_event.get("code")
            if isinstance(terminal_event.get("code"), str)
            else None
        ),
        retryable=(
            terminal_event.get("retryable")
            if isinstance(terminal_event.get("retryable"), bool)
            else None
        ),
    )


def _serialize_sse_event(payload: dict, request_id: str, sequence: int) -> str:
    """用标准 SSE id 和注释携带诊断元数据，保持 data JSON 向后兼容。"""

    timestamp = datetime.now(timezone.utc).isoformat()
    metadata = (
        f": protocol_version={_SSE_PROTOCOL_VERSION} "
        f"request_id={request_id} timestamp={timestamp}\n"
    )
    event_id = f"{request_id}:{sequence}"
    return (
        f"{metadata}id: {event_id}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
    )


class QueryService:
    """Orchestrate one question and expose graph events as SSE messages."""

    def __init__(
        self,
        meta_mysql_repository: MetaMySQLRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        dw_mysql_repository: DWMySQLRepository,
        column_qdrant_repository: ColumnQdrantRepository,
        cube_member_qdrant_repository: CubeMemberQdrantRepository,
        cube_repository: CubeRepository,
        value_es_repository: ValueESRepository,
        query_audit_repository: QueryAuditRepository | None = None,
        query_session_repository: QuerySessionRepository | None = None,
        query_message_repository: QueryMessageRepository | None = None,
        sse_event_repository: SSEEventRepository | None = None,
        query_export_repository: QueryExportRepository | None = None,
        result_object_store: ResultObjectStore | None = None,
        metadata_release_repository: MetadataReleaseRepository | None = None,
        semantic_model_repository: SemanticModelRepository | None = None,
        semantic_metric_relation_service: SemanticMetricRelationService | None = None,
        metric_candidate_repository: MetricCandidateRepository | None = None,
        sql_fallback_repository: SQLFallbackRepository | None = None,
        sql_policy_engine: SQLPolicyEngine | None = None,
        query_turn_context_repository: QueryTurnContextRepository | None = None,
        cache_service: CacheService | None = None,
        metrics: QueryMetrics | None = None,
    ):
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository
        self.embedding_client = embedding_client
        self.column_qdrant_repository = column_qdrant_repository
        self.cube_member_qdrant_repository = cube_member_qdrant_repository
        self.cube_repository = cube_repository
        self.value_es_repository = value_es_repository
        self.query_audit_repository = query_audit_repository
        self.query_session_repository = query_session_repository
        self.query_message_repository = query_message_repository
        self.sse_event_repository = sse_event_repository
        self.query_export_repository = query_export_repository
        self.result_object_store = result_object_store
        self.metadata_release_repository = metadata_release_repository
        self.semantic_model_repository = semantic_model_repository
        self.semantic_metric_relation_service = (
            semantic_metric_relation_service or SemanticMetricRelationService()
        )
        self.metric_candidate_repository = metric_candidate_repository
        self.sql_fallback_repository = sql_fallback_repository
        self.sql_policy_engine = sql_policy_engine
        self.query_turn_context_repository = query_turn_context_repository
        self.cache_service = cache_service
        self.metrics = metrics or get_query_metrics()

    async def _load_semantic_model_snapshot(self, budget: RequestBudget):
        """Best-effort load on its isolated session within the request budget."""

        if self.semantic_model_repository is None:
            return None
        timeout_seconds = min(
            _SEMANTIC_SNAPSHOT_TIMEOUT_SECONDS,
            budget.remaining_seconds(),
        )
        if timeout_seconds <= 0:
            return None
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self.semantic_model_repository.get_active_snapshot()
        except TimeoutError:
            logger.warning("Active semantic model snapshot read timed out")
        except Exception:
            logger.warning("Failed to read active semantic model snapshot")
        return None

    async def _externalize_result(
        self,
        payload: dict,
        *,
        request_id: str,
        user_id: str,
        policy_version: int,
        session_id: str | None,
    ) -> dict:
        """把超出 SSE 内联阈值的结果保存到 MinIO，只向客户端发送预览。"""

        data = payload.get("data")
        inline_bytes = len(
            json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        )
        if inline_bytes <= app_config.sse.max_inline_result_bytes:
            return payload
        if self.query_export_repository is None or self.result_object_store is None:
            raise QueryExecutionError(
                "result_export_unavailable", "结果过大且导出存储未就绪", False
            )

        export_id = str(uuid4())
        object_key = f"query-results/{export_id}.json"
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            seconds=app_config.minio.export_ttl_seconds
        )
        export_document = {
            "request_id": request_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "row_count": payload.get("row_count")
            if payload.get("row_count") is not None
            else (len(data) if isinstance(data, list) else None),
            "data": data,
        }
        object_bytes = json.dumps(
            export_document, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode("utf-8")
        try:
            await self.result_object_store.put_json(object_key, object_bytes)
            await self.query_export_repository.create(
                export_id=export_id,
                request_id=request_id,
                user_id=user_id,
                policy_version=policy_version,
                session_id=session_id,
                object_key=object_key,
                result_bytes=len(object_bytes),
                row_count=export_document["row_count"],
                expires_at=expires_at,
            )
        except Exception as error:
            logger.warning(
                "Failed to save result export error_type={}", type(error).__name__
            )
            try:
                await self.result_object_store.delete(object_key)
            except Exception:
                logger.warning("Failed to clean up result export object")
            raise QueryExecutionError(
                "result_export_unavailable", "结果导出暂不可用，请稍后重试", False
            ) from error

        preview = (
            list(data[: app_config.sse.result_preview_rows])
            if isinstance(data, list)
            else []
        )
        output = dict(payload)
        output["data"] = preview
        output["row_count"] = export_document["row_count"]
        output["truncated"] = True
        output["export_id"] = export_id
        output["export_available"] = True
        output["export_expires_at"] = expires_at.replace(
            tzinfo=timezone.utc
        ).isoformat()
        return output

    async def query(
        self,
        query: str,
        principal: QueryPrincipal,
        lease: AdmissionLease | None = None,
        session_id: str | None = None,
        include_attached_metrics: bool = True,
    ):
        """Execute one graph run and yield SSE-formatted events."""

        try:
            if lease is None:
                lease = await get_resource_admission().acquire(principal.auth.user_id)
            budget = RequestBudget.from_timeout(
                app_config.resource.request_timeout_seconds,
                max_llm_calls=app_config.resource.max_llm_calls,
                max_embedding_calls=app_config.resource.max_embedding_calls,
            )
        except QueryExecutionError as e:
            error = {
                "type": "error",
                "code": e.code,
                "message": e.message,
                "retryable": e.retryable,
            }
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
            return

        metadata_release_version = None
        if self.metadata_release_repository is not None:
            try:
                metadata_release_version = (
                    await self.metadata_release_repository.get_active_version()
                )
            except Exception:
                logger.warning("Failed to read active metadata release")
        if self.meta_mysql_repository is not None:
            self.meta_mysql_repository.set_release_version(metadata_release_version)

        recent_turn_contexts = []
        if (
            app_config.conversation.enabled
            and self.query_turn_context_repository is not None
            and session_id is not None
        ):
            try:
                recent_turn_contexts = (
                    await self.query_turn_context_repository.list_recent_successful(
                        session_id,
                        principal.auth.user_id,
                        limit=app_config.conversation.recent_turns,
                        max_context_chars=app_config.conversation.max_context_chars,
                    )
                )
            except Exception:
                logger.warning("Failed to load query turn context")

        request_id = str(request_id_ctx_var.get())
        user_message_persisted = False
        user_message_sequence_no = None
        if self.query_message_repository is not None and session_id is not None:
            try:
                user_message = await self.query_message_repository.append_user_message(
                    session_id,
                    principal.auth.user_id,
                    request_id,
                    query,
                )
                user_message_persisted = user_message is not None
                if user_message is not None:
                    sequence_no = getattr(user_message, "sequence_no", None)
                    if isinstance(sequence_no, int) and not isinstance(
                        sequence_no, bool
                    ):
                        user_message_sequence_no = sequence_no
                if user_message_sequence_no is None:
                    user_message_sequence_no = await _lookup_user_message_sequence(
                        self.query_message_repository,
                        session_id,
                        principal.auth.user_id,
                        request_id,
                    )
            except Exception:
                logger.warning("Failed to save query user message")

        state = DataAgentState(
            query=query,
            original_query=query,
            effective_query=query,
            recent_turn_contexts=recent_turn_contexts,
            include_attached_metrics=include_attached_metrics,
        )
        context = DataAgentContext(
            column_qdrant_repository=self.column_qdrant_repository,
            embedding_client=self.embedding_client,
            cube_member_qdrant_repository=self.cube_member_qdrant_repository,
            cube_repository=self.cube_repository,
            value_es_repository=self.value_es_repository,
            meta_mysql_repository=self.meta_mysql_repository,
            dw_mysql_repository=self.dw_mysql_repository,
            sql_fallback_repository=self.sql_fallback_repository,
            sql_policy_engine=self.sql_policy_engine,
            permissions=principal.permissions,
            auth=principal.auth,
            metadata_release_version=metadata_release_version,
            resource_budget=budget,
            dependency_breakers=get_dependency_breakers(),
            cache_service=self.cache_service,
        )
        usage_callback = LLMUsageCallbackHandler()
        started_at = perf_counter()
        audit = {
            "query_mode": None,
            "route_reason": None,
            "metric_query": None,
            "cube_query": None,
            "sql": None,
            "outcome": "aborted",
            "error_code": None,
            "verified": None,
            "normalized_sql": None,
            "executed_sql": None,
            "sql_policy_outcome": None,
            "sql_rejection_reason": None,
            "sql_estimated_rows": None,
            "sql_query_cost": None,
            "result_row_count": None,
            "result_bytes": None,
            "result_truncated": None,
            "sql_execution_duration_ms": None,
            "turn_context": None,
        }
        node_started_at: dict[str, float] = {}
        event_sequence = 0
        terminal_sent = False
        snapshot_events: list[dict] = []
        terminal_event: dict = {"type": "error", "code": "internal_error"}
        turn_context_payload: dict[str, object] | None = None

        async def serialize(payload: dict) -> str:
            nonlocal event_sequence
            event_sequence += 1
            frame = _serialize_sse_event(payload, request_id, event_sequence)
            if self.sse_event_repository is not None:
                try:
                    await self.sse_event_repository.append_frame(
                        request_id, event_sequence, frame
                    )
                except Exception:
                    logger.warning("Failed to persist SSE event")
            return frame

        graph_stream = None
        pending_chunk = None
        try:
            semantic_model_snapshot = await self._load_semantic_model_snapshot(budget)
            if semantic_model_snapshot is not None:
                context["semantic_model_snapshot"] = semantic_model_snapshot
                context["semantic_metric_relation_service"] = (
                    self.semantic_metric_relation_service
                )
            async with asyncio.timeout(budget.remaining_seconds()):
                graph_stream = graph.astream(
                    input=state,
                    context=context,
                    stream_mode="custom",
                    config={"callbacks": [usage_callback]},
                ).__aiter__()
                pending_chunk = asyncio.create_task(graph_stream.__anext__())
                while True:
                    done, _ = await asyncio.wait(
                        {pending_chunk},
                        timeout=app_config.sse.heartbeat_seconds,
                    )
                    if not done:
                        if not terminal_sent:
                            yield await serialize({"type": "heartbeat"})
                        continue
                    try:
                        chunk = pending_chunk.result()
                    except StopAsyncIteration:
                        break
                    pending_chunk = asyncio.create_task(graph_stream.__anext__())
                    budget.check()
                    if isinstance(chunk, dict) and chunk.get("type") == "audit":
                        event_turn_context = _safe_turn_context_event(
                            chunk.get("turn_context")
                        )
                        if event_turn_context is not None:
                            turn_context_payload = event_turn_context
                            audit["turn_context"] = event_turn_context
                        for field in _AUDIT_EVENT_FIELDS:
                            if field == "turn_context":
                                continue
                            if chunk.get(field) is not None:
                                audit[field] = chunk[field]
                        continue
                    if isinstance(chunk, dict) and chunk.get("type") == "metrics":
                        chunk = dict(chunk)
                        chunk["data"] = safe_metric_display_items(chunk.get("data"))
                    if isinstance(chunk, dict) and chunk.get("type") == "progress":
                        step = chunk.get("step")
                        status = chunk.get("status")
                        if isinstance(step, str) and status == "running":
                            node_started_at[step] = perf_counter()
                        elif isinstance(step, str) and status in {"success", "error"}:
                            node_started = node_started_at.pop(step, None)
                            if node_started is not None:
                                self.metrics.record_node(
                                    step,
                                    (perf_counter() - node_started) * 1000,
                                    status,
                                )
                    if isinstance(chunk, dict) and chunk.get("type") == "result":
                        chunk = await self._externalize_result(
                            chunk,
                            request_id=request_id,
                            user_id=principal.auth.user_id,
                            policy_version=principal.permissions.policy_version,
                            session_id=session_id,
                        )
                    if isinstance(chunk, dict) and chunk.get("type") in {
                        "result",
                        "error",
                        "cancelled",
                    }:
                        if terminal_sent:
                            logger.warning(
                                "忽略重复 SSE 终态 event_type={}", chunk.get("type")
                            )
                            continue
                        terminal_sent = True
                        terminal_event = dict(chunk)
                    elif isinstance(chunk, dict) and chunk.get("type") in {
                        "progress",
                        "metrics",
                        "route",
                    }:
                        snapshot_events.append(dict(chunk))
                    if isinstance(chunk, dict) and chunk.get("type") == "route":
                        audit["query_mode"] = chunk.get("mode")
                        audit["route_reason"] = chunk.get("reason")
                    elif isinstance(chunk, dict) and chunk.get("type") == "result":
                        audit["outcome"] = "success"
                        audit["verified"] = chunk.get("verified")
                        if turn_context_payload is not None:
                            result_summary = _terminal_result_summary(chunk)
                            existing_summary = turn_context_payload.get(
                                "result_summary"
                            )
                            merged_summary = (
                                dict(existing_summary)
                                if isinstance(existing_summary, dict)
                                else {}
                            )
                            merged_summary.update(result_summary)
                            turn_context_payload["result_summary"] = merged_summary
                    yield await serialize(chunk)
                if not terminal_sent:
                    terminal_sent = True
                    audit["outcome"] = "error"
                    audit["error_code"] = "missing_terminal_event"
                    terminal_event = {
                        "type": "error",
                        "code": "missing_terminal_event",
                        "message": "问数流程未返回最终状态",
                        "retryable": False,
                    }
                    yield await serialize(terminal_event)
        except TimeoutError:
            logger.warning("Question execution exceeded resource deadline")
            audit["outcome"] = "error"
            audit["error_code"] = "resource_deadline_exceeded"
            error = {
                "type": "error",
                "code": "resource_deadline_exceeded",
                "message": "问数请求已超过时间预算",
                "retryable": False,
            }
            if not terminal_sent:
                terminal_sent = True
                terminal_event = error
                yield await serialize(error)
        except asyncio.CancelledError:
            audit["outcome"] = "cancelled"
            terminal_event = {"type": "cancelled"}
            raise
        except QueryExecutionError as e:
            logger.error("Question execution failed code={}", e.code)
            audit["outcome"] = "error"
            audit["error_code"] = e.code
            error = {
                "type": "error",
                "code": e.code,
                "message": e.message,
                "retryable": e.retryable,
            }
            if not terminal_sent:
                terminal_sent = True
                terminal_event = error
                yield await serialize(error)
        except Exception:
            logger.error("Unexpected question execution error")
            audit["outcome"] = "error"
            audit["error_code"] = "internal_error"
            error = {
                "type": "error",
                "code": "internal_error",
                "message": "服务内部错误，请稍后重试",
                "retryable": False,
            }
            if not terminal_sent:
                terminal_sent = True
                terminal_event = error
                yield await serialize(error)
        finally:
            if pending_chunk is not None and not pending_chunk.done():
                pending_chunk.cancel()
                await asyncio.gather(pending_chunk, return_exceptions=True)
            if graph_stream is not None:
                await graph_stream.aclose()
            duration_ms = max(0, round((perf_counter() - started_at) * 1000))
            if node_started_at:
                node_outcome = (
                    "cancelled" if audit["outcome"] == "cancelled" else "error"
                )
                node_finished_at = perf_counter()
                for step, node_started in node_started_at.items():
                    self.metrics.record_node(
                        step,
                        (node_finished_at - node_started) * 1000,
                        node_outcome,
                    )
            self.metrics.record_request(
                duration_ms=duration_ms,
                outcome=audit["outcome"],
                route=audit["query_mode"],
                error_code=audit["error_code"],
            )
            # 先释放请求准入槽，再执行审计等持久化，避免持久化阻塞导致并发槽泄漏。
            if lease is not None:
                await lease.release()
            if self.query_audit_repository is not None:
                llm_input_tokens, llm_output_tokens = usage_callback.totals()
                record = QueryAuditRecord(
                    user_id=principal.auth.user_id,
                    username=principal.auth.username,
                    roles=tuple(sorted(principal.auth.roles)),
                    policy_version=principal.permissions.policy_version,
                    allowed_department_ids=tuple(
                        sorted(principal.permissions.allowed_department_ids)
                    ),
                    authz_outcome=(
                        "allowed"
                        if principal.permissions.allowed_department_ids
                        else "denied"
                    ),
                    query_text=query,
                    query_mode=audit["query_mode"],
                    route_reason=audit["route_reason"],
                    metric_query=audit["metric_query"],
                    cube_query=audit["cube_query"],
                    sql=audit["sql"],
                    outcome=audit["outcome"],
                    error_code=audit["error_code"],
                    verified=audit["verified"],
                    duration_ms=duration_ms,
                    normalized_sql=audit["normalized_sql"],
                    executed_sql=audit["executed_sql"],
                    sql_policy_outcome=audit["sql_policy_outcome"],
                    sql_rejection_reason=audit["sql_rejection_reason"],
                    sql_estimated_rows=audit["sql_estimated_rows"],
                    sql_query_cost=audit["sql_query_cost"],
                    result_row_count=audit["result_row_count"],
                    result_bytes=audit["result_bytes"],
                    result_truncated=audit["result_truncated"],
                    sql_execution_duration_ms=audit["sql_execution_duration_ms"],
                    llm_call_count=budget.llm_calls,
                    embedding_call_count=budget.embedding_calls,
                    llm_input_tokens=llm_input_tokens,
                    llm_output_tokens=llm_output_tokens,
                    llm_cost_units=None,
                    metadata_release_version=metadata_release_version,
                    session_id=session_id,
                )
                try:
                    await self.query_audit_repository.save(record)
                except Exception:
                    logger.warning("Failed to save query audit record")
            if (
                self.query_message_repository is not None
                and session_id is not None
                and user_message_persisted
            ):
                try:
                    snapshot = build_query_message_snapshot(
                        snapshot_events,
                        terminal_event,
                    )
                    await self.query_message_repository.append_assistant_message(
                        session_id,
                        principal.auth.user_id,
                        request_id,
                        snapshot,
                        metadata_release_version=metadata_release_version,
                    )
                except Exception:
                    logger.warning("Failed to save query assistant message")
            if (
                self.query_turn_context_repository is not None
                and session_id is not None
                and terminal_event.get("type") == "result"
                and audit["outcome"] == "success"
                and turn_context_payload is not None
                and user_message_sequence_no is not None
            ):
                try:
                    context_payload = dict(turn_context_payload)
                    context_payload["metadata_release_version"] = (
                        context_payload.get("metadata_release_version")
                        or metadata_release_version
                    )
                    turn_context = QueryTurnContext(
                        context_id=str(uuid4()),
                        session_id=session_id,
                        user_id=principal.auth.user_id,
                        request_id=request_id,
                        user_message_sequence_no=user_message_sequence_no,
                        effective_query=str(
                            context_payload.get("effective_query") or query
                        ),
                        query_mode=str(
                            context_payload.get("query_mode") or audit["query_mode"]
                        ),
                        context=(
                            context_payload.get("context")
                            if isinstance(context_payload.get("context"), dict)
                            else {}
                        ),
                        result_summary=(
                            context_payload.get("result_summary")
                            if isinstance(context_payload.get("result_summary"), dict)
                            else None
                        ),
                        metadata_release_version=context_payload.get(
                            "metadata_release_version"
                        ),
                        inherited_from_context_id=context_payload.get(
                            "inherited_from_context_id"
                        ),
                        context_schema_version=1,
                        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                    await self.query_turn_context_repository.save_if_absent(
                        turn_context
                    )
                except Exception:
                    logger.warning("Failed to save query turn context")
            if (
                (self.query_message_repository is None or not user_message_persisted)
                and self.query_session_repository is not None
                and session_id is not None
            ):
                try:
                    await self.query_session_repository.touch(
                        session_id,
                        principal.auth.user_id,
                        outcome=audit["outcome"],
                        query_mode=audit["query_mode"],
                        error_code=audit["error_code"],
                        metadata_release_version=metadata_release_version,
                    )
                except Exception:
                    logger.warning("Failed to update query session")
            if (
                self.metric_candidate_repository is not None
                and audit["query_mode"] == "sql"
            ):
                try:
                    await self.metric_candidate_repository.upsert_pending(
                        query, audit["route_reason"]
                    )
                except Exception:
                    logger.warning("Failed to save metric governance candidate")
