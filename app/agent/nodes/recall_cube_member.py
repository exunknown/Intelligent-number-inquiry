"""Cube 受治理成员召回节点。"""

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.log import logger
from app.core.resource_governance import await_with_budget
from app.entities.cube_member import CubeMember
from app.security.resource_filter import filter_cube_members


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
        cache_service = runtime.context.get("cache_service")
        terms = list(dict.fromkeys([state["query"], *state["keywords"]]))
        measures: dict[str, CubeMember] = {}
        dimensions: dict[str, CubeMember] = {}
        permissions = runtime.context["permissions"]
        resource_budget = runtime.context.get("resource_budget")
        breakers = runtime.context.get("dependency_breakers", {})
        metadata_release_version = runtime.context.get("metadata_release_version")
        try:
            index_generation = await await_with_budget(
                repository.get_alias_target(),
                resource_budget,
                circuit_breaker=breakers.get("qdrant"),
                dependency="qdrant",
            )
        except Exception:
            logger.warning("Cube member recall cache generation lookup failed")
            index_generation = None

        for term in terms:

            async def load_embedding() -> list[float]:
                return await await_with_budget(
                    embedding_client.aembed_query(term),
                    resource_budget,
                    resource="embedding",
                    circuit_breaker=breakers.get("embedding"),
                    dependency="embedding",
                )

            if cache_service is None:
                embedding = await load_embedding()
            else:
                embedding, _ = await cache_service.get_embedding(
                    term,
                    model_version=app_config.embedding.model,
                    dimension=app_config.qdrant.embedding_size,
                    loader=load_embedding,
                )

            async def load_members(member_types):
                return await await_with_budget(
                    repository.search(embedding, member_types),
                    resource_budget,
                    circuit_breaker=breakers.get("qdrant"),
                    dependency="qdrant",
                )

            async def cached_members(member_types):
                if (
                    cache_service is None
                    or metadata_release_version is None
                    or index_generation is None
                ):
                    return await load_members(member_types)
                try:
                    result, _ = await cache_service.get_cube_member_recall(
                        {
                            "metadata_release_version": metadata_release_version,
                            "index_generation": index_generation,
                            "recall_type": "cube_member",
                            "term": term,
                            "score_threshold": 0.6,
                            "limit": 10,
                            "member_types": sorted(member_types),
                        },
                        lambda: load_members(member_types),
                    )
                    return result
                except Exception:
                    logger.warning(
                        "Cube member recall cache failed; falling back to source"
                    )
                    return await load_members(member_types)

            _append_unseen(
                measures,
                filter_cube_members(
                    await cached_members({"measure"}),
                    permissions,
                ),
            )
            _append_unseen(
                dimensions,
                filter_cube_members(
                    await cached_members({"dimension", "time_dimension"}),
                    permissions,
                ),
            )

        async def load_catalog() -> list[CubeMember]:
            return await await_with_budget(
                repository.list_members(),
                resource_budget,
                circuit_breaker=breakers.get("qdrant"),
                dependency="qdrant",
            )

        if (
            cache_service is not None
            and metadata_release_version is not None
            and index_generation is not None
        ):
            try:
                public_catalog_members, _ = await cache_service.get_cube_catalog(
                    {
                        "metadata_release_version": metadata_release_version,
                        "index_generation": index_generation,
                        "recall_type": "cube_catalog",
                    },
                    load_catalog,
                )
            except Exception:
                logger.warning("Cube catalog cache failed; falling back to source")
                public_catalog_members = await load_catalog()
        else:
            public_catalog_members = await load_catalog()

        catalog_members = filter_cube_members(public_catalog_members, permissions)
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
        logger.error("{} failed error_type={}", step, type(exc).__name__)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
