"""
电商问数 Agent 图编排

使用 LangGraph 把问数智能体的各个节点串成一条可观测的执行链路
当前链路先并行召回字段 字段取值和 Cube 受治理成员，优先执行指标查询，
语义未覆盖时进入受控 Text-to-SQL 兜底链路
"""

import asyncio

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.agent.context import DataAgentContext
from app.agent.nodes.add_extra_context import add_extra_context
from app.agent.nodes.apply_selector import apply_selector
from app.agent.nodes.correct_sql import correct_sql
from app.agent.nodes.estimate_sql import estimate_sql
from app.agent.nodes.execute_cube_query import execute_cube_query
from app.agent.nodes.extract_keywords import extract_keywords
from app.agent.nodes.generate_metric_query import generate_metric_query
from app.agent.nodes.generate_sql import generate_sql
from app.agent.nodes.merge_retrieved_info import merge_retrieved_info
from app.agent.nodes.recall_column import recall_column
from app.agent.nodes.recall_cube_member import recall_cube_member
from app.agent.nodes.recall_value import recall_value
from app.agent.nodes.route_selector import route_selector
from app.agent.nodes.run_sql import run_sql
from app.agent.nodes.selector_agent import selector_agent
from app.agent.nodes.semantic_coverage_gate import semantic_coverage_gate
from app.agent.nodes.sql_security_gate import sql_security_gate
from app.agent.nodes.validate_metric_query import validate_metric_query
from app.agent.nodes.validate_sql import validate_sql
from app.agent.state import DataAgentState
from app.clients.cube_client_manager import get_cube_client_manager
from app.clients.embedding_client_manager import get_embedding_client_manager
from app.clients.es_client_manager import get_es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import get_qdrant_client_manager
from app.conf.app_config import app_config
from app.entities.auth import AuthContext, PermissionSnapshot
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)


def route_query_mode(state: DataAgentState) -> str:
    """按已确定的查询模式进入受治理指标或 SQL 兜底分支。"""

    return state["query_mode"]


# StateGraph 声明整张图使用的状态结构和运行时上下文结构
graph_builder = StateGraph(state_schema=DataAgentState, context_schema=DataAgentContext)

# 注册节点：每个节点负责问数链路中的一个清晰步骤
graph_builder.add_node("extract_keywords", extract_keywords)
graph_builder.add_node("recall_column", recall_column)
graph_builder.add_node("recall_value", recall_value)
graph_builder.add_node("recall_cube_member", recall_cube_member)
graph_builder.add_node("merge_retrieved_info", merge_retrieved_info)
graph_builder.add_node("semantic_coverage_gate", semantic_coverage_gate)
graph_builder.add_node("generate_metric_query", generate_metric_query)
graph_builder.add_node("validate_metric_query", validate_metric_query)
graph_builder.add_node("execute_cube_query", execute_cube_query)
graph_builder.add_node("sql_security_gate", sql_security_gate)
graph_builder.add_node("route_selector", route_selector)
graph_builder.add_node("selector_agent", selector_agent)
graph_builder.add_node("apply_selector", apply_selector)
graph_builder.add_node("add_extra_context", add_extra_context)
graph_builder.add_node("generate_sql", generate_sql)
graph_builder.add_node("validate_sql", validate_sql)
graph_builder.add_node("correct_sql", correct_sql)
graph_builder.add_node("estimate_sql", estimate_sql)
graph_builder.add_node("run_sql", run_sql)

# 从用户问题开始，先抽取关键词作为后续检索的基础
graph_builder.add_edge(START, "extract_keywords")

# 关键词抽取后并行进入三类召回，分别面向字段 字段值和 Cube 受治理成员
graph_builder.add_edge("extract_keywords", "recall_column")
graph_builder.add_edge("extract_keywords", "recall_value")
graph_builder.add_edge("extract_keywords", "recall_cube_member")

# 三路召回都完成后，再进入统一的信息合并节点
graph_builder.add_edge("recall_column", "merge_retrieved_info")
graph_builder.add_edge("recall_value", "merge_retrieved_info")
graph_builder.add_edge("recall_cube_member", "merge_retrieved_info")

# 优先尝试受治理指标链路；语义未覆盖或 unmatched 决策在阶段 1 由安全门禁拒绝
graph_builder.add_edge("merge_retrieved_info", "semantic_coverage_gate")
graph_builder.add_conditional_edges(
    source="semantic_coverage_gate",
    path=route_query_mode,
    path_map={"metric": "generate_metric_query", "sql": "sql_security_gate"},
)
graph_builder.add_edge("generate_metric_query", "validate_metric_query")
graph_builder.add_conditional_edges(
    source="validate_metric_query",
    path=route_query_mode,
    path_map={"metric": "execute_cube_query", "sql": "sql_security_gate"},
)
graph_builder.add_edge("execute_cube_query", END)
graph_builder.add_edge("sql_security_gate", "route_selector")

# SQL 兜底先经过 Token Gate，小 Schema 跳过 Selector
graph_builder.add_conditional_edges(
    source="route_selector",
    path=lambda state: (
        "selector_agent" if state["selector_enabled"] else "add_extra_context"
    ),
    path_map={
        "selector_agent": "selector_agent",
        "add_extra_context": "add_extra_context",
    },
)
graph_builder.add_edge("selector_agent", "apply_selector")
graph_builder.add_edge("apply_selector", "add_extra_context")

# Selector 分支裁剪完成后，统一补充生成 SQL 所需的上下文
graph_builder.add_edge("add_extra_context", "generate_sql")
graph_builder.add_edge("generate_sql", "validate_sql")

# SQL 校验通过后先做数据库成本检查；首次可修正错误回到校正节点
graph_builder.add_conditional_edges(
    source="validate_sql",
    path=lambda state: (
        "estimate_sql" if state["sql_validation_error"] is None else "correct_sql"
    ),
    path_map={"estimate_sql": "estimate_sql", "correct_sql": "correct_sql"},
)
graph_builder.add_edge("correct_sql", "validate_sql")
graph_builder.add_edge("estimate_sql", "run_sql")
graph_builder.add_edge("run_sql", END)

# 编译后的 graph 是对外使用的 Agent 执行入口
graph = graph_builder.compile()

# print(graph.get_graph().draw_mermaid())

if __name__ == "__main__":
    from app.scripts.sync_cube_metadata import _close_embedding_client

    async def test():
        """本地调试 Cube 指标优先与 SQL 兜底链路"""

        qdrant_manager = get_qdrant_client_manager()
        embedding_manager = get_embedding_client_manager()
        es_manager = get_es_client_manager()
        cube_manager = get_cube_client_manager()

        try:
            # 多路召回和上下文补全会访问 Qdrant、Embedding、ES、Cube 和 MySQL
            qdrant_manager.init()
            embedding_manager.init()
            es_manager.init()
            cube_manager.init()
            meta_mysql_client_manager.init()
            dw_mysql_client_manager.init()

            # Meta MySQL 用来补齐元数据，DW MySQL 用来读取数据库方言和版本
            async with (
                meta_mysql_client_manager.session_factory() as meta_session,
                dw_mysql_client_manager.session_factory() as dw_session,
            ):
                meta_mysql_repository = MetaMySQLRepository(meta_session)
                dw_mysql_repository = DWMySQLRepository(dw_session)

                # 字段和 Cube 成员分别使用不同 Qdrant collection，取值检索使用 ES index
                column_qdrant_repository = ColumnQdrantRepository(qdrant_manager.client)
                cube_member_qdrant_repository = CubeMemberQdrantRepository(
                    qdrant_manager.client
                )
                cube_repository = CubeRepository(cube_manager.client, app_config.cube)
                value_es_repository = ValueESRepository(es_manager.client)

                # 当前只需要传入原始问题，后续节点会逐步写回召回、过滤和额外上下文结果
                state = DataAgentState(
                    query="统计华北地区的销售总额",
                    include_attached_metrics=True,
                )
                context = DataAgentContext(
                    column_qdrant_repository=column_qdrant_repository,
                    embedding_client=embedding_manager.client,
                    cube_member_qdrant_repository=cube_member_qdrant_repository,
                    cube_repository=cube_repository,
                    value_es_repository=value_es_repository,
                    meta_mysql_repository=meta_mysql_repository,
                    dw_mysql_repository=dw_mysql_repository,
                    permissions=PermissionSnapshot(
                        policy_version=0,
                        allowed_metrics=frozenset({"ecommerce.gmv"}),
                        allowed_tables=frozenset(),
                        allowed_columns=frozenset({"dim_region.region_name"}),
                        allowed_department_ids=frozenset({"D001"}),
                        sql_fallback_allowed=False,
                    ),
                    auth=AuthContext(
                        user_id="local-debug",
                        username="local-debug",
                        roles=frozenset({"analyst"}),
                        token_id=None,
                        issued_at=0,
                        expires_at=0,
                    ),
                )

                # stream_mode="custom" 会接收节点通过 writer 写出的进度信息
                async for chunk in graph.astream(
                    input=state, context=context, stream_mode="custom"
                ):
                    print(chunk)
        finally:
            # 图执行失败时也统一释放显式创建的异步客户端
            await asyncio.gather(
                qdrant_manager.close(),
                es_manager.close(),
                cube_manager.close(),
                meta_mysql_client_manager.close(),
                dw_mysql_client_manager.close(),
                _close_embedding_client(embedding_manager.client),
                return_exceptions=True,
            )

    asyncio.run(test())
