"""Execute the final SQL fallback query."""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger


async def run_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """Execute SQL and mark the result as requiring manual review."""

    writer = runtime.stream_writer
    step = "执行SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        sql = state["sql"]
        writer({"type": "audit", "sql": sql, "query_mode": "sql"})
        dw_mysql_repository = runtime.context["dw_mysql_repository"]
        result = await dw_mysql_repository.run(sql)
        logger.info("SQL query result: {}", result)
        writer({"type": "progress", "step": step, "status": "success"})
        writer(
            {
                "type": "result",
                "data": result,
                "source": "sql",
                "verified": False,
                "warning": "该结果由 Text-to-SQL 生成，未经业务口径验证，请人工核对。",
            }
        )
    except Exception as e:
        logger.error("{} failed: {}", step, e)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
