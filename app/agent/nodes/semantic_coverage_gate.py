"""Cube 语义覆盖快速门控节点。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState


async def semantic_coverage_gate(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
):
    """仅用度量候选判断是否需要直接回退 SQL。"""

    if not state["retrieved_cube_measures"]:
        reason = "no_measure_candidate"
        runtime.stream_writer({"type": "route", "mode": "sql", "reason": reason})
        return {"query_mode": "sql", "route_reason": reason}
    return {"query_mode": "metric"}
