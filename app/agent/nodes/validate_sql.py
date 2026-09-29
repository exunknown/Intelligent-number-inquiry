"""使用 AST 策略引擎校验并重写模型 SQL。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.query_errors import QueryExecutionError
from app.entities.sql_execution import SQLPolicyInput
from app.security.sql_policy import SQLPolicyReason, SQLPolicyViolation

_CORRECTABLE_REASONS = frozenset(
    {SQLPolicyReason.INVALID_SQL, SQLPolicyReason.IDENTIFIER_UNRESOLVED}
)


async def validate_sql(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
):
    """只允许首次语法或标识符错误进入自动修正。"""

    writer = runtime.stream_writer
    step = "校验SQL"
    writer({"type": "progress", "step": step, "status": "running"})
    schema = {
        table["name"]: frozenset(column["name"] for column in table["columns"])
        for table in state["table_infos"]
    }
    if "fact_order" in schema:
        schema["fact_order"] = schema["fact_order"] | {"department_id"}

    try:
        result = runtime.context["sql_policy_engine"].prepare(
            SQLPolicyInput(
                raw_sql=state["raw_sql"],
                schema=schema,
                permissions=runtime.context["permissions"],
            )
        )
    except SQLPolicyViolation as exc:
        reason = exc.reason.value
        attempts = state.get("sql_correction_attempts", 0)
        writer(
            {
                "type": "audit",
                "sql_policy_outcome": "rejected",
                "sql_rejection_reason": reason,
            }
        )
        if exc.reason in _CORRECTABLE_REASONS and attempts == 0:
            writer({"type": "progress", "step": step, "status": "success"})
            return {"sql_validation_error": reason}
        writer({"type": "progress", "step": step, "status": "error"})
        raise QueryExecutionError(
            "sql_rejected", "SQL 查询未通过安全检查", False
        ) from None

    writer({"type": "progress", "step": step, "status": "success"})
    writer(
        {
            "type": "audit",
            "normalized_sql": result.normalized_sql,
            "executed_sql": result.executable_sql,
            "sql_policy_outcome": "allowed",
            "sql_rejection_reason": None,
        }
    )
    return {
        "normalized_sql": result.normalized_sql,
        "executable_sql": result.executable_sql,
        "sql_validation_error": None,
    }
