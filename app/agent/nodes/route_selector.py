"""Route between the full-context path and the conditional Selector path."""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.metric_display import legacy_metric_display_entries
from app.agent.selector import serialize_selector_candidates, should_use_selector
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.log import logger


async def route_selector(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """根据候选 Schema 的估算 Token 数决定是否调用 Selector。"""

    writer = runtime.stream_writer
    step = "评估Schema规模"
    writer({"type": "progress", "step": step, "status": "running"})
    try:
        schema_text = serialize_selector_candidates(state["selector_candidates"])
        selector_enabled, token_count = should_use_selector(
            schema_text,
            threshold=app_config.selector.schema_token_threshold,
            chars_per_token=app_config.selector.token_estimate_chars_per_token,
        )
        selector_enabled = app_config.selector.enabled and selector_enabled
        logger.info(
            f"Schema 估算 Token 数：{token_count}，Selector 启用：{selector_enabled}"
        )
        if not selector_enabled:
            writer(
                {
                    "type": "metrics",
                    "data": legacy_metric_display_entries(state),
                }
            )
        writer({"type": "progress", "step": step, "status": "success"})
        return {
            "selector_enabled": selector_enabled,
            "schema_token_count": token_count,
        }
    except Exception as e:
        logger.error("{} failed error_type={}", step, type(e).__name__)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
