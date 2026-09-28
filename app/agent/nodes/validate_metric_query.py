"""Validate Metric Query IR and select the governed or SQL route."""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.metric_query import validate_metric_query_result
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.query_errors import QueryExecutionError
from app.entities.metric_query import MetricQueryValidationError


async def validate_metric_query(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
):
    """Validate the generated IR and emit route plus internal audit data."""

    measure_names = [member.name for member in state["retrieved_cube_measures"]]
    try:
        decision = validate_metric_query_result(
            state["metric_query_raw"],
            measure_names,
            state["cube_member_catalog"],
            max_limit=app_config.cube.max_limit,
        )
    except MetricQueryValidationError as exc:
        raise QueryExecutionError(exc.code, str(exc), False) from exc

    if decision.status == "unmatched":
        reason = decision.reason
        runtime.stream_writer({"type": "route", "mode": "sql", "reason": reason})
        runtime.stream_writer(
            {
                "type": "audit",
                "metric_query": state["metric_query_raw"],
                "query_mode": "sql",
                "route_reason": reason,
            }
        )
        return {
            "metric_query_decision": decision,
            "query_mode": "sql",
            "route_reason": reason,
        }

    reason = "governed_measure_matched"
    runtime.stream_writer({"type": "route", "mode": "metric", "reason": reason})
    runtime.stream_writer(
        {
            "type": "audit",
            "metric_query": state["metric_query_raw"],
            "cube_query": decision.cube_query,
            "query_mode": "metric",
            "route_reason": reason,
        }
    )
    return {
        "cube_query": decision.cube_query,
        "metric_query_decision": decision,
        "query_mode": "metric",
        "route_reason": reason,
    }
