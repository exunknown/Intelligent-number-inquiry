"""Execute a validated Cube metric query."""

from dataclasses import asdict, is_dataclass
from typing import Any

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.metric_query import normalize_cube_result
from app.agent.state import DataAgentState, build_turn_context_payload
from app.core.log import logger


async def execute_cube_query(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """Execute a validated Cube query and emit a verified result."""

    writer = runtime.stream_writer
    step = "执行指标查询"
    writer({"type": "progress", "step": step, "status": "running"})
    writer(
        {
            "type": "audit",
            "cube_query": state["cube_query"],
            "query_mode": "metric",
        }
    )

    try:
        auth = runtime.context["auth"]
        permissions = runtime.context["permissions"]
        request_options = {}
        if resource_budget := runtime.context.get("resource_budget"):
            request_options["budget"] = resource_budget
        cube_query = state["cube_query"]

        async def load_metric_result() -> dict:
            response = await runtime.context["cube_repository"].load(
                cube_query,
                auth.user_id,
                permissions.allowed_department_ids,
                permissions.policy_version,
                **request_options,
            )
            return {
                "type": "result",
                "data": normalize_cube_result(response),
                "source": "metric",
                "verified": True,
                "warning": None,
            }

        cache_service = runtime.context.get("cache_service")
        metadata_release_version = runtime.context.get("metadata_release_version")
        metric_result_cacheable = state.get("metric_result_cacheable")
        if metric_result_cacheable is None:
            metric_result_cacheable = not _contains_high_volatility_value(
                state.get("metric_query_decision") or cube_query
            )
        if (
            cache_service is not None
            and metadata_release_version is not None
            and metric_result_cacheable
        ):
            try:
                result_payload, _ = await cache_service.get_metric_result(
                    cube_query,
                    metadata_release_version,
                    permissions,
                    auth.user_id,
                    load_metric_result,
                )
            except Exception:
                logger.warning("Metric result cache failed; falling back to Cube")
                result_payload = await load_metric_result()
        else:
            if cache_service is not None and not metric_result_cacheable:
                _record_volatile_cache_skip(cache_service)
            result_payload = await load_metric_result()
        result = result_payload["data"]
        logger.info("Cube query completed rows={}", len(result))
        writer(
            {
                "type": "audit",
                "turn_context": build_turn_context_payload(
                    {**state, "query_mode": "metric"},
                    {"row_count": len(result), "verified": True},
                ),
            }
        )
        writer({"type": "progress", "step": step, "status": "success"})
        writer(result_payload)
    except Exception as e:
        logger.error("{} failed error_type={}", step, type(e).__name__)
        writer({"type": "progress", "step": step, "status": "error"})
        raise


def _contains_high_volatility_value(value: Any) -> bool:
    """识别不适合缓存或需要极短 TTL 的实时语义。"""

    if is_dataclass(value):
        return _contains_high_volatility_value(asdict(value))
    if isinstance(value, str):
        normalized = value.strip().lower()
        return any(term in normalized for term in ("today", "latest", "real-time"))
    if isinstance(value, dict):
        return any(_contains_high_volatility_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_high_volatility_value(item) for item in value)
    return False


def _record_volatile_cache_skip(cache_service: object) -> None:
    metrics = getattr(cache_service, "metrics", None)
    if metrics is None:
        return
    try:
        metrics.record_cache("metric_result", "skipped", "volatile_query")
    except Exception:
        logger.warning("Metric cache skip metric failed; ignoring")
