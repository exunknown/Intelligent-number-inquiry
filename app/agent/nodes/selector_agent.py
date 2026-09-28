"""LLM Selector node with a strict, candidate-bound JSON contract."""

import json

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.selector import (
    serialize_selector_candidates,
    validate_selector_result,
)
from app.agent.state import DataAgentState
from app.core.log import logger
from app.prompt.prompt_loader import load_prompt


async def selector_agent(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """调用 Selector，只输出候选表和值的 JSON 选择结果。"""

    writer = runtime.stream_writer
    step = "Schema Selector"
    writer({"type": "progress", "step": step, "status": "running"})
    try:
        candidates = state["selector_candidates"]
        prompt = PromptTemplate(
            template=load_prompt("select_schema"),
            input_variables=["query", "candidates"],
        )
        chain = prompt | llm | JsonOutputParser()
        raw_result = await chain.ainvoke(
            {
                "query": state["query"],
                "candidates": serialize_selector_candidates(candidates),
            }
        )
        candidate_tables = {table["id"] for table in candidates["tables"]}
        candidate_values = {
            value["id"]: value["column_id"] for value in candidates["values"]
        }
        candidate_columns = {
            column["id"]
            for table in candidates["tables"]
            for column in table["columns"]
        }
        decision = validate_selector_result(
            raw_result,
            candidate_tables=candidate_tables,
            candidate_values=candidate_values,
            candidate_columns=candidate_columns,
        )
        logger.info(
            "Selector 结果：%s",
            json.dumps(decision, ensure_ascii=False, sort_keys=True),
        )
        writer({"type": "progress", "step": step, "status": "success"})
        return {"selector_decision": decision}
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
