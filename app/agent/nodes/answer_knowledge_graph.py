"""输出业务知识图谱关系结果节点。"""

from collections.abc import Mapping

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import (
    DataAgentState,
    build_graph_evidence,
    build_turn_context_payload,
)
from app.core.log import logger
from app.entities.knowledge_graph import BUSINESS_EDGE_TYPES, KnowledgeGraphNode

_EVIDENCE_KEYS = frozenset(
    {
        "order_count",
        "quantity",
        "sales_amount",
        "share",
        "period",
        "confidence",
    }
)


def _safe_evidence(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    evidence = {
        str(key): item
        for key, item in value.items()
        if str(key) in _EVIDENCE_KEYS and isinstance(item, (str, int, float, bool))
    }
    return evidence or None


def _relation_rows(state: DataAgentState) -> list[dict[str, object]]:
    nodes = {
        node.node_id: node
        for node in state.get("retrieved_graph_nodes", [])
        if isinstance(node, KnowledgeGraphNode)
    }
    rows: list[dict[str, object]] = []
    for edge in state.get("retrieved_graph_edges", []):
        if edge.edge_type not in BUSINESS_EDGE_TYPES:
            continue
        source = nodes.get(edge.source_node_id)
        target = nodes.get(edge.target_node_id)
        if source is None or target is None:
            continue
        row: dict[str, object] = {
            "source": source.title,
            "source_type": source.node_type,
            "relation": edge.edge_type,
            "target": target.title,
            "target_type": target.node_type,
            "weight": edge.weight,
        }
        evidence = _safe_evidence(edge.evidence)
        if evidence is not None:
            row["evidence"] = evidence
        rows.append(row)
    return rows


async def answer_knowledge_graph(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
) -> dict[str, object]:
    """把已授权、已脱敏的业务关系投影为现有结果事件。"""

    writer = runtime.stream_writer
    step = "返回业务关系"
    writer({"type": "progress", "step": step, "status": "running"})
    try:
        rows = _relation_rows(state)
        warning = (
            None
            if rows
            else "当前业务知识图谱没有返回可展示的关系证据，请补充更具体的业务对象。"
        )
        graph_evidence = build_graph_evidence(
            state,
            allowed_edge_types=BUSINESS_EDGE_TYPES,
        )
        writer(
            {
                "type": "route",
                "mode": "graph",
                "reason": "knowledge_graph_relation",
            }
        )
        writer(
            {
                "type": "audit",
                "query_mode": "graph",
                "turn_context": build_turn_context_payload(
                    {
                        **state,
                        "query_mode": "graph",
                        "graph_evidence": graph_evidence,
                    },
                    {"row_count": len(rows), "verified": False},
                ),
            }
        )
        writer({"type": "progress", "step": step, "status": "success"})
        writer(
            {
                "type": "result",
                "data": rows,
                "source": "graph",
                "verified": False,
                "warning": warning,
                "row_count": len(rows),
                "truncated": False,
            }
        )
        return {
            "query_mode": "graph",
            "route_reason": "knowledge_graph_relation",
        }
    except Exception as error:
        logger.error("{} failed error_type={}", step, type(error).__name__)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
