"""Execute a validated Cube metric query."""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.metric_query import normalize_cube_result
from app.agent.state import DataAgentState
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
        response = await runtime.context["cube_repository"].load(state["cube_query"])
        result = normalize_cube_result(response)
        logger.info("Cube query result: {}", result)
        writer({"type": "progress", "step": step, "status": "success"})
        writer(
            {
                "type": "result",
                "data": result,
                "source": "metric",
                "verified": True,
                "warning": None,
            }
        )
    except Exception as e:
        logger.error("{} failed: {}", step, e)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
