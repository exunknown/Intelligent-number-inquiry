"""
电商问数 Agent 运行上下文

Context 用来保存一次图执行过程中不参与状态合并的外部依赖或配置
本章放入多路召回需要的 Embedding 客户端 Qdrant 仓储和 ES 仓储
召回信息合并阶段还会访问 Meta MySQL，用于按 id 补齐字段和表结构元数据
额外上下文补全阶段会访问 DW MySQL，用于读取数据库方言和版本
这样节点可以通过 runtime.context 复用外部工具，而不需要把连接类对象塞进 State
"""

from typing import NotRequired, TypedDict

from langchain_huggingface import HuggingFaceEndpointEmbeddings

from app.core.resource_governance import RequestBudget
from app.entities.auth import AuthContext, PermissionSnapshot
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.dw.sql_fallback_repository import SQLFallbackRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.security.sql_policy import SQLPolicyEngine


class DataAgentContext(TypedDict):
    """LangGraph Runtime 中传递的上下文对象"""

    # 字段向量仓储，负责根据向量从 Qdrant 检索候选字段
    column_qdrant_repository: ColumnQdrantRepository
    # Embedding 客户端，负责把关键词转换成向量检索所需的 query vector
    embedding_client: HuggingFaceEndpointEmbeddings
    # Cube 受治理成员向量仓储，负责召回度量和维度候选及读取完整目录
    cube_member_qdrant_repository: CubeMemberQdrantRepository
    # Cube 查询仓储，负责执行已通过确定性校验的指标查询
    cube_repository: CubeRepository
    # 字段取值全文检索仓储，负责从 Elasticsearch 检索真实字段值
    value_es_repository: ValueESRepository
    # 元数据仓储，负责在召回结果合并时补齐字段 表 主外键等结构信息
    meta_mysql_repository: MetaMySQLRepository
    # 数仓仓储，负责在额外上下文补全时读取数据库方言 版本等执行环境信息
    dw_mysql_repository: DWMySQLRepository
    # SQL fallback 专用只读仓储，只接受策略引擎生成的最终执行 SQL
    sql_fallback_repository: SQLFallbackRepository
    # SQL AST 安全策略引擎，不访问外部服务
    sql_policy_engine: SQLPolicyEngine
    # 认证入口生成的一次请求权限快照，所有节点必须复用同一对象
    permissions: PermissionSnapshot
    # 已验证的用户身份，用于下游服务令牌的主体声明
    auth: AuthContext
    # 请求级端到端资源预算；调试入口和旧调用可暂不提供
    resource_budget: NotRequired[RequestBudget]
