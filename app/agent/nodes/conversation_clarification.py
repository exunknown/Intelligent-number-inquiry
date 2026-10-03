"""输出多轮问数需要用户确认的稳定终态。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.query_errors import CONVERSATION_CLARIFICATION_REQUIRED

_CLARIFICATION_MESSAGE = "请确认本次查询是否基于上一轮结果继续？"


async def conversation_clarification(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
) -> dict[str, object]:
    """结束澄清分支，不进入召回、Cube 或 SQL 执行链路。"""

    del state
    writer = runtime.stream_writer
    step = "澄清会话上下文"
    writer({"type": "progress", "step": step, "status": "running"})
    writer({"type": "progress", "step": step, "status": "error"})
    writer(
        {
            "type": "error",
            "code": CONVERSATION_CLARIFICATION_REQUIRED,
            "message": _CLARIFICATION_MESSAGE,
            "retryable": False,
        }
    )
    return {
        "conversation_mode": "clarification",
        "error": CONVERSATION_CLARIFICATION_REQUIRED,
    }
