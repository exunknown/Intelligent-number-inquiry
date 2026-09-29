"""Question execution service and SSE serialization."""

import asyncio
import json
from time import perf_counter

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.log import logger
from app.core.query_errors import QueryExecutionError
from app.core.resource_governance import (
    AdmissionLease,
    LLMUsageCallbackHandler,
    RequestBudget,
    get_dependency_breakers,
    get_resource_admission,
)
from app.entities.auth import QueryPrincipal
from app.entities.query_audit import QueryAuditRecord
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.dw.sql_fallback_repository import SQLFallbackRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.mysql.meta.metric_candidate_repository import (
    MetricCandidateRepository,
)
from app.repositories.mysql.meta.query_audit_repository import QueryAuditRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.security.sql_policy import SQLPolicyEngine

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
        metric_candidate_repository: MetricCandidateRepository | None = None,
        sql_fallback_repository: SQLFallbackRepository | None = None,
        sql_policy_engine: SQLPolicyEngine | None = None,
    ):
        self.meta_mysql_repository = meta_mysql_repository
        self.dw_mysql_repository = dw_mysql_repository
        self.embedding_client = embedding_client
        self.column_qdrant_repository = column_qdrant_repository
        self.cube_member_qdrant_repository = cube_member_qdrant_repository
        self.cube_repository = cube_repository
        self.value_es_repository = value_es_repository
        self.query_audit_repository = query_audit_repository
        self.metric_candidate_repository = metric_candidate_repository
        self.sql_fallback_repository = sql_fallback_repository
        self.sql_policy_engine = sql_policy_engine

    async def query(
        self,
        query: str,
        principal: QueryPrincipal,
        lease: AdmissionLease | None = None,
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

        state = DataAgentState(query=query)
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
            resource_budget=budget,
            dependency_breakers=get_dependency_breakers(),
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
        }
        try:
            async with asyncio.timeout(budget.remaining_seconds()):
                async for chunk in graph.astream(
                    input=state,
                    context=context,
                    stream_mode="custom",
                    config={"callbacks": [usage_callback]},
                ):
                    budget.check()
                    if isinstance(chunk, dict) and chunk.get("type") == "audit":
                        for field in _AUDIT_EVENT_FIELDS:
                            if chunk.get(field) is not None:
                                audit[field] = chunk[field]
                        continue
                    if isinstance(chunk, dict) and chunk.get("type") == "route":
                        audit["query_mode"] = chunk.get("mode")
                        audit["route_reason"] = chunk.get("reason")
                    elif isinstance(chunk, dict) and chunk.get("type") == "result":
                        audit["outcome"] = "success"
                        audit["verified"] = chunk.get("verified")
                    yield f"data: {json.dumps(chunk, ensure_ascii=False, default=str)}\n\n"
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
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            audit["outcome"] = "cancelled"
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
            yield f"data: {json.dumps(error, ensure_ascii=False, default=str)}\n\n"
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
            yield f"data: {json.dumps(error, ensure_ascii=False, default=str)}\n\n"
        finally:
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
                    duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
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
                )
                try:
                    await self.query_audit_repository.save(record)
                except Exception:
                    logger.warning("Failed to save query audit record")
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
            if lease is not None:
                await lease.release()
