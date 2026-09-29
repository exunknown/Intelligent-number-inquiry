"""
SQL 修正节点

负责在 SQL 校验失败后，结合原问题 原 SQL 数据库错误和完整上下文做最小必要修正
只有 validate_sql 写入错误信息时，LangGraph 才会进入这个分支
"""

import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.core.log import logger
from app.core.resource_governance import await_with_budget
from app.prompt.prompt_loader import load_prompt


async def correct_sql(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """根据校验错误修正 SQL"""

    writer = runtime.stream_writer
    step = "校正SQL"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # 校正 SQL 仍然需要完整上下文，避免模型只根据报错修语法却改丢业务语义
        table_infos = state["table_infos"]
        metric_infos = state["metric_infos"]
        date_info = state["date_info"]
        db_info = state["db_info"]
        query = state["query"]

        sql = state["raw_sql"]
        error_code = state["sql_validation_error"]
        resource_budget = runtime.context.get("resource_budget")
        llm_breaker = runtime.context.get("dependency_breakers", {}).get("llm")

        prompt = PromptTemplate(
            template=load_prompt("correct_sql"),
            input_variables=[
                "table_infos",
                "metric_infos",
                "date_info",
                "db_info",
                "query",
                "sql",
                "error_code",
            ],
        )
        # 修正后的输出仍然是一条纯 SQL 文本，用来覆盖 state["sql"]
        output_parser = StrOutputParser()
        chain = prompt | llm | output_parser

        result = await await_with_budget(
            chain.ainvoke(
                {
                    # 与生成节点保持一致，用 YAML 向模型提供稳定 可读的结构化上下文
                    "table_infos": yaml.dump(
                        table_infos, allow_unicode=True, sort_keys=False
                    ),
                    "metric_infos": yaml.dump(
                        metric_infos, allow_unicode=True, sort_keys=False
                    ),
                    "date_info": yaml.dump(
                        date_info, allow_unicode=True, sort_keys=False
                    ),
                    "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
                    "query": query,
                    "sql": sql,
                    "error_code": error_code,
                }
            ),
            resource_budget,
            resource="llm",
            circuit_breaker=llm_breaker,
            dependency="llm",
        )

        logger.info("SQL candidate corrected chars={}", len(result))
        writer({"type": "progress", "step": step, "status": "success"})
        writer({"type": "audit", "sql_correction_candidate": result})
        return {
            "sql": result,
            "raw_sql": result,
            "sql_correction_attempts": state.get("sql_correction_attempts", 0) + 1,
            "sql_validation_error": None,
        }
    except Exception:
        logger.error("SQL candidate correction failed")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
