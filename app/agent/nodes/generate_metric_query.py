"""受候选白名单约束的 Metric Query IR 生成节点。"""

import json
from datetime import datetime, timedelta, timezone

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import JsonOutputParser
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.metric_query import validate_metric_query_shape
from app.agent.state import DataAgentState, build_graph_evidence
from app.conf.app_config import app_config
from app.core.log import logger
from app.core.query_errors import QueryExecutionError
from app.core.resource_governance import await_with_budget
from app.entities.cube_member import CubeMember
from app.entities.metric_query import MetricQueryValidationError
from app.prompt.prompt_loader import load_prompt

_SHANGHAI_TIMEZONE = timezone(timedelta(hours=8), "Asia/Shanghai")
_FILTER_OPERATORS = [
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "is_set",
    "is_not_set",
]
_TIME_PRESETS = [
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_quarter",
    "last_quarter",
    "this_year",
    "last_year",
    "last_7_days",
    "last_30_days",
    "last_90_days",
]
_GRANULARITIES = ["day", "week", "month", "quarter", "year"]
_UNMATCHED_REASONS = [
    "no_measure_candidate",
    "missing_dimension_mapping",
    "unsupported_analysis",
    "ambiguous_measure",
]


async def invoke_metric_query_model(
    prompt_text: str, resource_budget=None, circuit_breaker=None
) -> object:
    """调用全局模型并把唯一 JSON 对象解析为 Python 值。"""

    chain = llm | JsonOutputParser()
    return await await_with_budget(
        chain.ainvoke(prompt_text),
        resource_budget,
        resource="llm",
        circuit_breaker=circuit_breaker,
        dependency="llm",
    )


def _candidate_payload(member: CubeMember, state: DataAgentState) -> dict:
    recalled_values = []
    if member.source_column_id is not None:
        recalled_values = list(
            dict.fromkeys(
                value.value
                for value in state.get("retrieved_value_infos", [])
                if value.column_id == member.source_column_id
            )
        )
    return {
        "name": member.name,
        "member_type": member.member_type,
        "data_type": member.data_type,
        "title": member.title,
        "description": member.description,
        "aliases": member.aliases,
        "ai_context": member.ai_context,
        "filterable": member.filterable,
        "recalled_values": recalled_values,
    }


def _build_prompt(state: DataAgentState, max_limit: int) -> str:
    candidates = [
        *state["retrieved_cube_measures"],
        *state["retrieved_cube_dimensions"],
    ]
    candidate_payload = [_candidate_payload(member, state) for member in candidates]
    matched_schema = {
        "status": "matched",
        "query": {
            "measures": ["cube.measure"],
            "dimensions": ["cube.dimension"],
            "filters": [
                {
                    "member": "cube.dimension",
                    "operator": "equals",
                    "values": ["value"],
                }
            ],
            "time": {
                "dimension": "cube.time_dimension",
                "range": {"type": "preset", "value": "last_30_days"},
                "granularity": "day",
            },
            "order_by": [{"member": "cube.measure", "direction": "desc"}],
            "limit": max_limit,
        },
    }
    unmatched_schema = {
        "status": "unmatched",
        "reason": "unsupported_analysis",
    }
    sections = [
        load_prompt("generate_metric_query").rstrip(),
        f"Current date: {datetime.now(_SHANGHAI_TIMEZONE).date().isoformat()}",
        "Matched JSON schema (optional query fields may be omitted):",
        json.dumps(matched_schema, ensure_ascii=False, indent=2),
        "Unmatched JSON schema:",
        json.dumps(unmatched_schema, ensure_ascii=False, indent=2),
        "Allowed filter operators: " + json.dumps(_FILTER_OPERATORS),
        "Allowed time presets: " + json.dumps(_TIME_PRESETS),
        "Allowed time granularities: " + json.dumps(_GRANULARITIES),
        "Approved unmatched reasons: " + json.dumps(_UNMATCHED_REASONS),
        f"Maximum query limit: {max_limit}",
        "Member candidates JSON:",
        json.dumps(candidate_payload, ensure_ascii=False, indent=2),
        "Metric graph evidence JSON:",
        json.dumps(
            build_graph_evidence(
                state,
                allowed_edge_types={
                    "METRIC_EQUIVALENT_TO",
                    "METRIC_ATTACHED_TO",
                    "MEASURE_DEPENDS_ON_MEMBER",
                },
                allowed_node_types={
                    "semantic_member",
                    "metric_equivalence_group",
                },
            ),
            ensure_ascii=False,
            indent=2,
        ),
        "Question:",
        state["query"],
    ]
    return "\n".join(sections)


def _repair_prompt(base_prompt: str, invalid: object, message: str) -> str:
    return "\n".join(
        [
            base_prompt,
            "Previous invalid object:",
            json.dumps(invalid, ensure_ascii=False, indent=2, default=str),
            "Validation message:",
            message,
            "Return one corrected JSON object using the same candidate whitelist.",
        ]
    )


async def generate_metric_query(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
):
    """生成并严格校验 Metric Query 结构，失败时只修复一次。"""

    writer = runtime.stream_writer
    step = "生成 Metric Query"
    writer({"type": "progress", "step": step, "status": "running"})
    max_limit = app_config.cube.max_limit
    base_prompt = _build_prompt(state, max_limit)
    resource_budget = getattr(runtime, "context", {}).get("resource_budget")
    llm_breaker = (
        getattr(runtime, "context", {}).get("dependency_breakers", {}).get("llm")
    )
    invalid: object = "<unparseable>"
    try:
        try:
            invalid = await invoke_metric_query_model(
                base_prompt, resource_budget, llm_breaker
            )
            validated = validate_metric_query_shape(invalid, max_limit=max_limit)
        except (OutputParserException, MetricQueryValidationError) as first_error:
            if isinstance(first_error, OutputParserException):
                invalid = first_error.llm_output or invalid
            repair_prompt = _repair_prompt(base_prompt, invalid, str(first_error))
            try:
                repaired = await invoke_metric_query_model(
                    repair_prompt, resource_budget, llm_breaker
                )
                validated = validate_metric_query_shape(repaired, max_limit=max_limit)
            except (
                OutputParserException,
                MetricQueryValidationError,
            ) as second_error:
                raise QueryExecutionError(
                    "invalid_model_output", str(second_error), False
                ) from second_error

        writer({"type": "progress", "step": step, "status": "success"})
        return {"metric_query_raw": validated}
    except Exception as exc:
        logger.error("{} failed error_type={}", step, type(exc).__name__)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
