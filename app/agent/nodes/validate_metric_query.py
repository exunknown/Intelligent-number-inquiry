"""Validate Metric Query IR and select the governed or SQL route."""

from dataclasses import replace

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.metric_query import to_cube_query, validate_metric_query_result
from app.agent.state import DataAgentState
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
    first_primary: CubeMember | None = None
    attached_members: list[CubeMember] = []

    for requested_name in decision.query.measures:
        resolution = relation_service.resolve(
            requested_name,
            snapshot,
            permissions,
            member_catalog,
            expand_attachments=state.get("include_attached_metrics", True),
        )
        if resolution.primary is None:
            members = (
                (member_catalog[requested_name],)
                if requested_name in permissions.allowed_metrics
                else ()
            )
            primary_by_requested[requested_name] = requested_name
        else:
            members = resolution.members
            primary_by_requested[requested_name] = resolution.primary.name
            if first_primary is None:
                first_primary = resolution.primary
            attached_members.extend(
                attachment.member for attachment in resolution.attachments
            )

        for member in members:
            if (
                member.name in permissions.allowed_metrics
                and member.name not in seen_names
            ):
                seen_names.add(member.name)
                resolved_names.append(member.name)

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
    resolved_decision = replace(
        decision,
        query=query,
        cube_query=to_cube_query(query, member_catalog),
    )
    state_updates: dict = {
        "resolved_attached_metrics": list(
            {member.name: member for member in attached_members}.values()
        )
    }
    if first_primary is not None:
        state_updates["resolved_primary_metric"] = first_primary
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
            "type": "audit",
            "metric_query": state["metric_query_raw"],
            "cube_query": decision.cube_query,
            "query_mode": "metric",
            "route_reason": reason,
        }
    )
    return {
        "cube_query": decision.cube_query,
        "metric_query_decision": decision,
        "query_mode": "metric",
        "route_reason": reason,
        **relation_state,
    }
