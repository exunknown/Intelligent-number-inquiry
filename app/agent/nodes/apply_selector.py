"""Apply a validated Selector decision to SQL-facing context."""

from __future__ import annotations

from copy import deepcopy

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.selector import SelectorDecision
from app.agent.state import (
    DataAgentState,
    SelectorCandidatesState,
    TableInfoState,
)
from app.core.log import logger


def apply_selector_decision(
    table_infos: list[TableInfoState],
    candidates: SelectorCandidatesState,
    decision: SelectorDecision,
) -> list[TableInfoState]:
    """裁剪表和值，并保证不修改 LangGraph 中已有的输入对象。"""

    table_candidates_by_name = {table["name"]: table for table in candidates["tables"]}
    selected_values_by_column: dict[str, list[str]] = {}
    values_by_id = {value["id"]: value for value in candidates["values"]}
    for selected_value in decision["keep_values"]:
        value = values_by_id[selected_value["value_id"]]
        selected_values_by_column.setdefault(selected_value["column_id"], []).append(
            value["value"]
        )

    kept_table_ids = set(decision["keep_tables"])
    result: list[TableInfoState] = []
    for table_info in table_infos:
        table_candidate = table_candidates_by_name.get(table_info["name"])
        if table_candidate is None:
            raise ValueError(
                f"table is missing from selector candidates: {table_info['name']}"
            )
        if table_candidate["id"] not in kept_table_ids:
            continue

        copied_table = deepcopy(table_info)
        candidate_columns_by_name = {
            column["name"]: column for column in table_candidate["columns"]
        }
        for column_info in copied_table["columns"]:
            candidate_column = candidate_columns_by_name.get(column_info["name"])
            if candidate_column is None:
                raise ValueError(
                    f"column is missing from selector candidates: "
                    f"{table_info['name']}.{column_info['name']}"
                )
            selected_values = selected_values_by_column.get(candidate_column["id"])
            if selected_values is not None:
                column_info["examples"] = selected_values
        result.append(copied_table)

    return result


async def apply_selector(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """将已校验的 Selector JSON 应用到 SQL 生成上下文。"""

    writer = runtime.stream_writer
    step = "应用Schema筛选"
    writer({"type": "progress", "step": step, "status": "running"})
    try:
        table_infos = apply_selector_decision(
            state["table_infos"],
            state["selector_candidates"],
            state["selector_decision"],
        )
        logger.info(
            f"Selector 保留的表信息：{[table_info['name'] for table_info in table_infos]}"
        )
        writer(
            {
                "type": "metrics",
                "data": [
                    member.title or member.name
                    for member in state["retrieved_cube_measures"]
                ],
            }
        )
        writer({"type": "progress", "step": step, "status": "success"})
        return {"table_infos": table_infos}
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
