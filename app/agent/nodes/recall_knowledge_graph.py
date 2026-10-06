"""问数链路中的版本化知识图谱召回节点。"""

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger
from app.entities.knowledge_graph import (
    EDGE_TYPES,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
)

_ALLOWED_EDGE_TYPES = frozenset(
    {
        "MEMBER_IN_CUBE",
        "MEMBER_SOURCE_COLUMN",
        "MEASURE_DEPENDS_ON_MEMBER",
        "METRIC_EQUIVALENT_TO",
        "METRIC_ATTACHED_TO",
        "CUBE_ON_TABLE",
        "CUBE_JOIN_CUBE",
        "COLUMN_BELONGS_TO_TABLE",
        "COLUMN_REFERENCES_COLUMN",
        "VALUE_BELONGS_TO_COLUMN",
    }
)
_DEFAULT_CONFIG = {
    "enabled": False,
    "max_hops": 2,
    "max_nodes": 80,
    "max_paths": 20,
    "timeout_seconds": 0.25,
}


def _empty_result(*, enabled: bool, degraded: bool = False, seed_count: int = 0):
    return {
        "retrieved_graph_nodes": [],
        "retrieved_graph_edges": [],
        "graph_paths": [],
        "graph_evidence_summary": {
            "enabled": enabled,
            "degraded": degraded,
            "seed_count": seed_count,
            "node_count": 0,
            "edge_count": 0,
            "path_count": 0,
        },
    }


def _config_value(config: Any, key: str) -> Any:
    value = (
        config.get(key, _DEFAULT_CONFIG[key]) if isinstance(config, Mapping) else None
    )
    return _DEFAULT_CONFIG[key] if value is None else value


def _stable_member_node_id(member: object) -> str | None:
    name = getattr(member, "name", None)
    cube_name = getattr(member, "cube_name", None)
    member_type = getattr(member, "member_type", None)
    if not all(isinstance(item, str) and item.strip() for item in (name, cube_name)):
        return None
    if member_type not in {"measure", "dimension", "time_dimension"}:
        return None
    member_name = name.rsplit(".", 1)[-1]
    return f"member:{member_type}:{cube_name}:{member_name}"


def _seed_node_ids(state: DataAgentState) -> list[str]:
    seeds: list[str] = []

    def add(node_id: object) -> None:
        if isinstance(node_id, str) and node_id and node_id not in seeds:
            seeds.append(node_id)

    for column in state.get("retrieved_column_infos", []):
        add(f"column:{getattr(column, 'id', '')}")
    for value in state.get("retrieved_value_infos", []):
        column_id = getattr(value, "column_id", None)
        if isinstance(column_id, str):
            add(f"column:{column_id}")
        value_id = getattr(value, "id", None)
        if isinstance(value_id, str):
            add(f"value:{value_id}")
    for member in [
        *state.get("retrieved_cube_measures", []),
        *state.get("retrieved_cube_dimensions", []),
    ]:
        add(_stable_member_node_id(member))
        cube_name = getattr(member, "cube_name", None)
        if isinstance(cube_name, str):
            add(f"cube:{cube_name}")
        source_column_id = getattr(member, "source_column_id", None)
        if isinstance(source_column_id, str):
            add(f"column:{source_column_id}")
    return seeds


def _directly_allowed_node(node: KnowledgeGraphNode, permissions) -> bool:
    node_id = node.node_id
    if node.node_type == "table":
        return node_id.removeprefix("table:") in permissions.allowed_tables
    if node.node_type == "column":
        return node_id.removeprefix("column:") in permissions.allowed_columns
    if node.node_type == "value":
        column_id = node.payload.get("column_id")
        return isinstance(column_id, str) and column_id in permissions.allowed_columns
    if node.node_type == "semantic_member":
        member_type = node.payload.get("member_type")
        if member_type == "measure":
            member_name = node.payload.get("member_name")
            cube_name = node.payload.get("cube_name")
            if not isinstance(member_name, str) or not isinstance(cube_name, str):
                return False
            qualified_name = (
                member_name if "." in member_name else f"{cube_name}.{member_name}"
            )
            return qualified_name in permissions.allowed_metrics
        source_column_id = node.payload.get("source_column_id")
        return (
            isinstance(source_column_id, str)
            and source_column_id in permissions.allowed_columns
        )
    if node.node_type == "cube":
        table_id = node.payload.get("table")
        return (
            isinstance(table_id, str)
            and table_id.rsplit(".", 1)[-1] in permissions.allowed_tables
        )
    return False


def _authorized_node_ids(nodes, edges, permissions) -> set[str]:
    node_by_id = {node.node_id: node for node in nodes}
    authorized = {
        node.node_id for node in nodes if _directly_allowed_node(node, permissions)
    }
    contextual_types = {"cube", "business_term", "metric_equivalence_group"}
    changed = True
    while changed:
        changed = False
        for edge in edges:
            source = node_by_id.get(edge.source_node_id)
            target = node_by_id.get(edge.target_node_id)
            if source is None or target is None:
                continue
            if (
                edge.source_node_id in authorized
                and target.node_type in contextual_types
                and edge.target_node_id not in authorized
            ):
                authorized.add(edge.target_node_id)
                changed = True
            if (
                edge.target_node_id in authorized
                and source.node_type in contextual_types
                and edge.source_node_id not in authorized
            ):
                authorized.add(edge.source_node_id)
                changed = True
    return authorized


def _safe_projection(value: object) -> object:
    sensitive = {
        "authorization",
        "connection",
        "connection_info",
        "connection_string",
        "database",
        "database_url",
        "db",
        "dsn",
        "host",
        "hostname",
        "password",
        "prompt",
        "result",
        "rows",
        "secret",
        "sql",
        "token",
    }
    if isinstance(value, dict):
        return {
            str(key): _safe_projection(item)
            for key, item in value.items()
            if str(key).strip().lower() not in sensitive
        }
    if isinstance(value, list):
        return [_safe_projection(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_safe_projection(item) for item in value)
    return value


def _redact_node(node: KnowledgeGraphNode) -> KnowledgeGraphNode:
    return replace(node, payload=_safe_projection(node.payload))


def _redact_edge(edge: KnowledgeGraphEdge) -> KnowledgeGraphEdge:
    return replace(edge, evidence=_safe_projection(edge.evidence))


async def recall_knowledge_graph(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
    writer=None,
) -> dict[str, object]:
    """从当前发布版本召回有界图谱证据，故障时安全降级为空结果。"""

    writer = writer or runtime.stream_writer
    step = "知识图谱推理"
    writer({"type": "progress", "step": step, "status": "running"})
    context = runtime.context
    config = context.get("knowledge_graph_config", {})
    enabled = bool(_config_value(config, "enabled"))
    if not enabled:
        result = _empty_result(enabled=False)
        writer({"type": "progress", "step": step, "status": "completed"})
        return result

    seed_ids = _seed_node_ids(state)
    repository = context.get("knowledge_graph_repository")
    release_version = context.get("metadata_release_version")
    if (
        repository is None
        or not isinstance(release_version, str)
        or not release_version
    ):
        result = _empty_result(enabled=True, degraded=True, seed_count=len(seed_ids))
        writer({"type": "progress", "step": step, "status": "degraded"})
        return result
    if not seed_ids:
        result = _empty_result(enabled=True, seed_count=0)
        writer({"type": "progress", "step": step, "status": "completed"})
        return result

    try:
        max_hops = max(1, min(2, int(_config_value(config, "max_hops"))))
        max_nodes = max(1, int(_config_value(config, "max_nodes")))
        max_paths = max(1, int(_config_value(config, "max_paths")))
        timeout_seconds = float(_config_value(config, "timeout_seconds"))
        configured_edges = (
            config.get("allowed_edge_types") if isinstance(config, Mapping) else None
        )
        allowed_edges = (
            set(configured_edges) & _ALLOWED_EDGE_TYPES
            if configured_edges is not None
            else set(_ALLOWED_EDGE_TYPES)
        )
        allowed_edges &= EDGE_TYPES
        async with asyncio.timeout(max(timeout_seconds, 0.001)):
            nodes, edges, paths = await repository.expand_paths(
                release_version=release_version,
                seed_node_ids=seed_ids,
                allowed_edge_types=allowed_edges,
                max_hops=max_hops,
                max_nodes=max_nodes,
                max_paths=max_paths,
            )

        nodes = [node for node in nodes if node.release_version == release_version]
        edges = [edge for edge in edges if edge.release_version == release_version]
        node_ids = {node.node_id for node in nodes}
        paths = [
            path
            for path in paths
            if all(node_id in node_ids for node_id in path.node_ids)
        ]
        permissions = context["permissions"]
        authorized_ids = _authorized_node_ids(nodes, edges, permissions)
        filtered_nodes = [
            _redact_node(node) for node in nodes if node.node_id in authorized_ids
        ]
        filtered_edges = [
            _redact_edge(edge)
            for edge in edges
            if edge.source_node_id in authorized_ids
            and edge.target_node_id in authorized_ids
        ]
        filtered_paths = [
            path
            for path in paths
            if all(node_id in authorized_ids for node_id in path.node_ids)
        ]
        result = {
            "retrieved_graph_nodes": filtered_nodes,
            "retrieved_graph_edges": filtered_edges,
            "graph_paths": filtered_paths,
            "graph_evidence_summary": {
                "enabled": True,
                "degraded": False,
                "seed_count": len(seed_ids),
                "node_count": len(filtered_nodes),
                "edge_count": len(filtered_edges),
                "path_count": len(filtered_paths),
            },
        }
        writer({"type": "progress", "step": step, "status": "completed"})
        return result
    except Exception as error:
        logger.warning(
            "知识图谱召回降级 release_version={} seed_count={} error_type={} degraded=true",
            release_version,
            len(seed_ids),
            type(error).__name__,
        )
        result = _empty_result(enabled=True, degraded=True, seed_count=len(seed_ids))
        writer({"type": "progress", "step": step, "status": "degraded"})
        return result
