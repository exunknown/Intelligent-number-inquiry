"""执行 SQL fallback 的数据库成本门禁。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.query_errors import QueryExecutionError


async def estimate_sql(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
):
    """只对最终执行 SQL 做 MySQL JSON EXPLAIN。"""

    writer = runtime.stream_writer
    step = "评估SQL成本"
    writer({"type": "progress", "step": step, "status": "running"})
    repository = runtime.context.get("sql_fallback_repository")
    if repository is None:
        writer({"type": "progress", "step": step, "status": "error"})
        raise QueryExecutionError(
            "sql_security_not_ready", "SQL 安全执行能力尚未启用", False
        )

    try:
        estimate = await repository.explain(state["executable_sql"])
    except Exception:
        writer({"type": "progress", "step": step, "status": "error"})
        raise

    value = {
        "estimated_rows": estimate.estimated_rows,
        "query_cost": estimate.query_cost,
    }
    writer(
        {
            "type": "audit",
            "sql_estimated_rows": estimate.estimated_rows,
            "sql_query_cost": estimate.query_cost,
        }
    )
    writer({"type": "progress", "step": step, "status": "success"})
    return {"sql_cost_estimate": value}
