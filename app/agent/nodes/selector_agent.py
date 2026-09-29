"""LLM Selector node with a strict, candidate-bound JSON contract."""

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
from app.core.resource_governance import await_with_budget
from app.prompt.prompt_loader import load_prompt


async def selector_agent(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """调用 Selector，只输出候选表和值的 JSON 选择结果。"""

    writer = runtime.stream_writer
    step = "Schema Selector"
    writer({"type": "progress", "step": step, "status": "running"})
    try:
        candidates = state["selector_candidates"]
        resource_budget = runtime.context.get("resource_budget")
        llm_breaker = runtime.context.get("dependency_breakers", {}).get("llm")
        prompt = PromptTemplate(
            template=load_prompt("select_schema"),
            input_variables=["query", "candidates"],
        )
        chain = prompt | llm | JsonOutputParser()
        raw_result = await await_with_budget(
            chain.ainvoke(
                {
                    "query": state["query"],
                    "candidates": serialize_selector_candidates(candidates),
                }
            ),
            resource_budget,
            resource="llm",
            circuit_breaker=llm_breaker,
            dependency="llm",
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
            "Selector 已完成表数量={} 值数量={}",
            len(decision["keep_tables"]),
            len(decision["keep_values"]),
        )
        writer({"type": "progress", "step": step, "status": "success"})
        return {"selector_decision": decision}
    except Exception as e:
        logger.error("{} failed error_type={}", step, type(e).__name__)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
