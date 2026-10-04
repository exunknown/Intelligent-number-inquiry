"""Validate Metric Query IR and select the governed or SQL route."""

from dataclasses import replace

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.metric_display import governed_metric_display_entries
from app.agent.metric_query import validate_metric_query_result
from app.agent.state import DataAgentState, build_turn_context_payload
from app.conf.app_config import app_config
from app.core.query_errors import QueryExecutionError
from app.entities.cube_member import CubeMember
from app.entities.metric_query import MetricQueryDecision, MetricQueryValidationError


def _resolve_metric_relations(
    state: DataAgentState,
    runtime: Runtime[DataAgentContext],
    decision: MetricQueryDecision,
) -> tuple[MetricQueryDecision, dict]:
    """Apply active semantic relations to the final authorized measure list."""

    context = getattr(runtime, "context", {})
    snapshot = context.get("semantic_model_snapshot")
    relation_service = context.get("semantic_metric_relation_service")
    permissions = context.get("permissions")
    if (
        decision.status != "matched"
        or decision.query is None
        or snapshot is None
        or relation_service is None
        or permissions is None
    ):
        return decision, {}

    member_catalog = state["cube_member_catalog"]
    resolved_names: list[str] = []
    seen_names: set[str] = set()
    primary_by_requested: dict[str, str] = {}
    primary_metrics: list[CubeMember] = []
    compatibility_notes: dict[str, str] = {}
    explicit_metrics: list[tuple[str, CubeMember]] = []
    attached_members: list[CubeMember] = []
    attached_sources: dict[str, str] = {}

    for requested_name in decision.query.measures:
        resolution = relation_service.resolve(
            requested_name,
            snapshot,
            permissions,
            member_catalog,
            expand_attachments=False,
        )
        if resolution.primary is None:
            primary = (
                member_catalog[requested_name]
                if requested_name in permissions.allowed_metrics
                else None
            )
            primary_by_requested[requested_name] = requested_name
        else:
            primary = resolution.primary
            primary_by_requested[requested_name] = resolution.primary.name

        if primary is None or primary.name not in permissions.allowed_metrics:
            continue
        explicit_metrics.append((requested_name, primary))
        if primary.name not in {member.name for member in primary_metrics}:
            primary_metrics.append(primary)
        if resolution.compatibility_notes:
            compatibility_notes[primary.name] = "；".join(
                resolution.compatibility_notes
            )
        if primary.name not in seen_names:
            seen_names.add(primary.name)
            resolved_names.append(primary.name)

    explicit_primary_names = frozenset(resolved_names)
    if state.get("include_attached_metrics", True):
        for requested_name, _ in explicit_metrics:
            expanded = relation_service.resolve(
                requested_name,
                snapshot,
                permissions,
                member_catalog,
                expand_attachments=True,
            )
            for attachment in expanded.attachments:
                normalized = relation_service.resolve(
                    attachment.member,
                    snapshot,
                    permissions,
                    member_catalog,
                    expand_attachments=False,
                )
                member = normalized.primary or attachment.member
                if (
                    member.name in explicit_primary_names
                    or member.name not in permissions.allowed_metrics
                    or member.name in seen_names
                ):
                    continue
                seen_names.add(member.name)
                resolved_names.append(member.name)
                attached_members.append(member)
                attached_sources[member.name] = attachment.source_member_id

    if not resolved_names:
        raise QueryExecutionError(
            "invalid_model_output",
            "No permitted metric remains after resolution",
            False,
        )

    resolved_orders = []
    seen_order_members = set()
    for order in decision.query.order_by:
        member_name = primary_by_requested.get(order.member, order.member)
        if member_name in seen_order_members:
            continue
        seen_order_members.add(member_name)
        resolved_orders.append(replace(order, member=member_name))

    query = replace(
        decision.query,
        measures=tuple(resolved_names),
        order_by=tuple(resolved_orders),
    )
    cube_query = dict(decision.cube_query or {})
    cube_query["measures"] = list(query.measures)
    if query.order_by:
        cube_query["order"] = {
            order.member: order.direction for order in query.order_by
        }
    else:
        cube_query.pop("order", None)
    resolved_decision = replace(
        decision,
        query=query,
        cube_query=cube_query,
    )
    state_updates: dict = {
        "resolved_primary_metrics": primary_metrics,
        "resolved_attached_metrics": attached_members,
        "resolved_attached_metric_sources": attached_sources,
        "resolved_compatibility_notes": compatibility_notes,
    }
    if primary_metrics:
        state_updates["resolved_primary_metric"] = primary_metrics[0]
    return resolved_decision, state_updates


async def validate_metric_query(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
):
    """Validate the generated IR and emit route plus internal audit data."""

    measure_names = [member.name for member in state["retrieved_cube_measures"]]
    try:
        decision = validate_metric_query_result(
            state["metric_query_raw"],
            measure_names,
            state["cube_member_catalog"],
            max_limit=app_config.cube.max_limit,
        )
        decision, relation_state = _resolve_metric_relations(state, runtime, decision)
    except MetricQueryValidationError as exc:
        raise QueryExecutionError(exc.code, str(exc), False) from exc

    if decision.status == "unmatched":
        reason = decision.reason
        runtime.stream_writer({"type": "route", "mode": "sql", "reason": reason})
        runtime.stream_writer(
            {
                "type": "audit",
                "metric_query": state["metric_query_raw"],
                "query_mode": "sql",
                "route_reason": reason,
                "turn_context": build_turn_context_payload(
                    {
                        **state,
                        "metric_query_decision": decision,
                        "query_mode": "sql",
                    },
                    None,
                ),
            }
        )
        return {
            "metric_query_decision": decision,
            "query_mode": "sql",
            "route_reason": reason,
        }

    reason = "governed_measure_matched"
    runtime.stream_writer({"type": "route", "mode": "metric", "reason": reason})
    runtime.stream_writer(
        {
            "type": "metrics",
            "data": governed_metric_display_entries({**state, **relation_state}),
        }
    )
    runtime.stream_writer(
        {
            "type": "audit",
            "metric_query": state["metric_query_raw"],
            "cube_query": decision.cube_query,
            "query_mode": "metric",
            "route_reason": reason,
            "turn_context": build_turn_context_payload(
                {
                    **state,
                    **relation_state,
                    "metric_query_decision": decision,
                    "query_mode": "metric",
                },
                None,
            ),
        }
    )
    return {
        "cube_query": decision.cube_query,
        "metric_query_decision": decision,
        "query_mode": "metric",
        "route_reason": reason,
        **relation_state,
    }
