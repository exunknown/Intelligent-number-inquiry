"""阶段 01 的 SQL 兜底安全闸门。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.query_errors import QueryExecutionError


async def sql_security_gate(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
) -> None:
    """在 AST 安全能力交付前稳定拒绝所有 SQL 兜底。"""

    del state
    step = "SQL 安全检查"
    runtime.stream_writer({"type": "progress", "step": step, "status": "running"})
    runtime.stream_writer({"type": "progress", "step": step, "status": "error"})
    raise QueryExecutionError(
        "sql_security_not_ready", "SQL 安全执行能力尚未启用", False
    )
