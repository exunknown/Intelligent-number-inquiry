"""SQL 兜底执行前的 fail-closed 安全闸门。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.query_errors import QueryExecutionError


async def sql_security_gate(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
) -> None:
    """依次检查功能开关、执行权限与部门数据范围。"""

    del state
    step = "SQL 安全检查"
    runtime.stream_writer({"type": "progress", "step": step, "status": "running"})
    permissions = runtime.context["permissions"]
    if not app_config.sql_safety.enabled:
        error = QueryExecutionError(
            "sql_security_not_ready", "SQL 安全执行能力尚未启用", False
        )
    elif not permissions.sql_fallback_allowed:
        error = QueryExecutionError("forbidden_resource", "无权执行 SQL 查询", False)
    elif not permissions.allowed_department_ids:
        error = QueryExecutionError(
            "no_data_scope", "当前用户没有可查询的数据范围", False
        )
    else:
        runtime.stream_writer({"type": "progress", "step": step, "status": "success"})
        return None

    runtime.stream_writer({"type": "progress", "step": step, "status": "error"})
    raise error
