"""
字段召回节点

负责根据关键词从字段向量知识库中召回候选字段
它解决的是“用户问题可能对应哪些数据库字段”的问题
本章的主线是：关键词扩展 -> Embedding -> Qdrant 相似度检索 -> ColumnInfo 去重
"""

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.llm import llm
from app.agent.state import DataAgentState
from app.conf.app_config import app_config
from app.core.log import logger
from app.core.resource_governance import await_with_budget
from app.entities.column_info import ColumnInfo
from app.prompt.prompt_loader import load_prompt
from app.security.resource_filter import filter_columns


async def recall_column(state: DataAgentState, runtime: Runtime[DataAgentContext]):
    """召回和用户问题语义相关的字段元数据"""

    writer = runtime.stream_writer
    step = "召回字段信息"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        # state 保存图内业务中间结果：原始问题和上游抽取出的关键词
        keywords = state["keywords"]
        query = state["query"]
        # context 保存外部运行时工具：向量仓储和 Embedding 客户端
        column_qdrant_repository = runtime.context["column_qdrant_repository"]
        embedding_client = runtime.context["embedding_client"]
        cache_service = runtime.context.get("cache_service")
        resource_budget = runtime.context.get("resource_budget")
        breakers = runtime.context.get("dependency_breakers", {})
        metadata_release_version = runtime.context.get("metadata_release_version")
        try:
            index_generation = await await_with_budget(
                column_qdrant_repository.get_alias_target(),
                resource_budget,
                circuit_breaker=breakers.get("qdrant"),
                dependency="qdrant",
            )
        except Exception:
            logger.warning("Column recall cache generation lookup failed")
            index_generation = None

        # 用 LLM 把用户问法扩展成“字段语义”列表，例如“销售总额”可扩展出“销售金额”
        prompt = PromptTemplate(
            template=load_prompt("extend_keywords_for_column_recall"),
            input_variables=["query"],
        )
        # 提示词要求模型只输出 JSON 数组，解析后 result 就是 list[str]
        output_parser = JsonOutputParser()
        # LCEL 管道：填充提示词 -> 调用模型 -> 解析 JSON
        chain = prompt | llm | output_parser

        result = await await_with_budget(
            chain.ainvoke({"query": query}),
            resource_budget,
            resource="llm",
            circuit_breaker=breakers.get("llm"),
            dependency="llm",
        )

        # 原始关键词和 LLM 扩展词一起参与召回；set 去重，避免重复请求同一关键词
        keywords = set(keywords + result)

        # 用字段 id 做唯一键，因为多个关键词、同一字段的多个向量点都可能命中同一个字段
        column_info_map: dict[str, ColumnInfo] = {}
        for keyword in keywords:
            # 查询词必须先转成向量，才能和第 9 章写入 Qdrant 的字段向量做相似度检索
            async def load_embedding() -> list[float]:
                return await await_with_budget(
                    embedding_client.aembed_query(keyword),
                    resource_budget,
                    resource="embedding",
                    circuit_breaker=breakers.get("embedding"),
                    dependency="embedding",
                )

            if cache_service is None:
                embedding = await load_embedding()
            else:
                embedding, _ = await cache_service.get_embedding(
                    keyword,
                    model_version=app_config.embedding.model,
                    dimension=app_config.qdrant.embedding_size,
                    loader=load_embedding,
                )

            async def load_recall() -> list[ColumnInfo]:
                return await await_with_budget(
                    column_qdrant_repository.search(embedding),
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
                    current_column_infos, _ = await cache_service.get_column_recall(
                        {
                            "metadata_release_version": metadata_release_version,
                            "index_generation": index_generation,
                            "recall_type": "column",
                            "term": keyword,
                            "score_threshold": 0.6,
                            "limit": 20,
                        },
                        load_recall,
                    )
                except Exception:
                    logger.warning("Column recall cache failed; falling back to source")
                    current_column_infos = await load_recall()
            else:
                current_column_infos = await load_recall()
            for column_info in current_column_infos:
                if column_info.id not in column_info_map:
                    column_info_map[column_info.id] = column_info

        # 写回 state 的是去重后的 ColumnInfo 列表，不暴露 Qdrant 原始 point 结构
        retrieved_column_infos = filter_columns(
            list(column_info_map.values()), runtime.context["permissions"]
        )

        writer({"type": "progress", "step": step, "status": "success"})
        return {"retrieved_column_infos": retrieved_column_infos}
    except Exception as e:
        logger.error("{} failed error_type={}", step, type(e).__name__)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
