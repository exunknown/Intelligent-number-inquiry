"""Cube 受治理成员召回节点。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.entities.cube_member import CubeMember


def _append_unseen(target: dict[str, CubeMember], members: list[CubeMember]) -> None:
    for member in members:
        if member.name not in target:
            target[member.name] = member


async def recall_cube_member(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """不扩展关键词，直接召回 Cube 度量、维度和完整成员目录。"""

    writer = runtime.stream_writer
    step = "召回 Cube 成员"
    writer({"type": "progress", "step": step, "status": "running"})
    try:
        repository = runtime.context["cube_member_qdrant_repository"]
        embedding_client = runtime.context["embedding_client"]
        terms = list(dict.fromkeys([state["query"], *state["keywords"]]))
        measures: dict[str, CubeMember] = {}
        dimensions: dict[str, CubeMember] = {}

        for term in terms:
            embedding = await embedding_client.aembed_query(term)
            _append_unseen(
                measures,
                await repository.search(embedding, {"measure"}),
            )
            _append_unseen(
                dimensions,
                await repository.search(embedding, {"dimension", "time_dimension"}),
            )

        catalog_members = await repository.list_members()
        _append_unseen(
            measures,
            [member for member in catalog_members if member.member_type == "measure"],
        )
        _append_unseen(
            dimensions,
            [
                member
                for member in catalog_members
                if member.member_type == "time_dimension"
            ],
        )
        result = {
            "retrieved_cube_measures": list(measures.values()),
            "retrieved_cube_dimensions": list(dimensions.values()),
            "cube_member_catalog": {member.name: member for member in catalog_members},
        }
        writer({"type": "progress", "step": step, "status": "success"})
        return result
    except Exception as exc:
        logger.error(f"{step} failed: {exc}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
