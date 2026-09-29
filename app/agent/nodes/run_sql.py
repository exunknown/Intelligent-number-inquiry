"""执行经过策略与成本门禁的最终 SQL。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.core.query_errors import QueryExecutionError


async def run_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """使用专用只读仓储执行 SQL，并输出结果规模。"""

    writer = runtime.stream_writer
    step = "执行SQL"
    writer({"type": "progress", "step": step, "status": "running"})
    repository = runtime.context.get("sql_fallback_repository")
    if repository is None:
        writer({"type": "progress", "step": step, "status": "error"})
        raise QueryExecutionError(
            "sql_security_not_ready", "SQL 安全执行能力尚未启用", False
        )

    try:
        result = await repository.run(state["executable_sql"])
    except Exception:
        writer({"type": "progress", "step": step, "status": "error"})
        raise

    stats = {
        "row_count": result.row_count,
        "result_bytes": result.result_bytes,
        "truncated": result.truncated,
        "duration_ms": result.duration_ms,
    }
    logger.info(
        "SQL fallback completed rows={} bytes={} truncated={} duration_ms={}",
        result.row_count,
        result.result_bytes,
        result.truncated,
        result.duration_ms,
    )
    writer({"type": "audit", **stats})
    writer({"type": "progress", "step": step, "status": "success"})
    writer(
        {
            "type": "result",
            "data": list(result.rows),
            "source": "sql",
            "verified": False,
            "warning": "该结果由 Text-to-SQL 生成，未经业务口径验证，请人工核对。",
            "row_count": result.row_count,
            "truncated": result.truncated,
        }
    )
    return {"sql_result_stats": stats}
