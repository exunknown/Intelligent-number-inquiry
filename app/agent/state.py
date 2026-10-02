"""
电商问数 Agent 状态定义

State 是 LangGraph 各节点之间传递和更新的共享数据
本章在用户原始问题之外，新增关键词列表和三路召回结果
并把召回到的实体整理成后续提示词更容易消费的表信息和指标信息
SQL 生成闭环会继续写入候选 SQL 以及校验错误信息，用于控制校正或执行分支
"""

from typing import Literal, NotRequired, TypedDict

from app.agent.selector import SelectorDecision
from app.entities.column_info import ColumnInfo
from app.entities.cube_member import CubeMember
from app.entities.metric_info import MetricInfo
from app.entities.metric_query import MetricQueryDecision, SemanticMissReason
from app.entities.value_info import ValueInfo


class MetricInfoState(TypedDict):
    """面向 SQL 生成提示词的指标信息"""

    name: str
    description: str
    # 指标依赖的字段 id，用来提示模型不要脱离业务口径随意计算
    relevant_columns: list[str]
    alias: list[str]


class ColumnInfoState(TypedDict):
    """表上下文中的字段信息"""

    name: str
    type: str
    role: str
    # 字段真实样例值，尤其用于辅助 where 条件里的枚举值选择
    examples: list
    description: str
    alias: list[str]


class TableInfoState(TypedDict):
    """SQL 生成阶段真正传给模型的表结构上下文"""

    name: str
    role: str
    description: str
    columns: list[ColumnInfoState]


class DateInfoState(TypedDict):
    """SQL 生成阶段使用的当前日期上下文"""

    date: str
    weekday: str
    quarter: str


class DBInfoState(TypedDict):
    """SQL 生成阶段使用的数据库环境信息"""

    dialect: str
    version: str


class SelectorColumnState(TypedDict):
    """带稳定 ID 的 Selector 字段候选"""

    id: str
    table_id: str
    name: str
    type: str
    role: str
    examples: list
    description: str
    alias: list[str]


class SelectorTableState(TypedDict):
    """带稳定 ID 的 Selector 表候选"""

    id: str
    name: str
    role: str
    description: str
    columns: list[SelectorColumnState]


class SelectorMetricState(TypedDict):
    """带稳定 ID 的 Selector 指标候选"""

    id: str
    name: str
    description: str
    relevant_columns: list[str]
    alias: list[str]


class SelectorValueState(TypedDict):
    """带稳定 ID 的 Selector 字段值候选"""

    id: str
    value: str
    column_id: str


class SelectorCandidatesState(TypedDict):
    """Selector 使用的、可被严格校验的候选证据"""

    tables: list[SelectorTableState]
    metrics: list[SelectorMetricState]
    values: list[SelectorValueState]


class DataAgentState(TypedDict):
    """一次问数链路中的核心状态"""

    query: str  # 用户输入的查询
    keywords: list[str]  # 抽取的关键词
    retrieved_column_infos: list[ColumnInfo]  # 检索到的字段信息
    retrieved_metric_infos: list[MetricInfo]  # 检索到的指标信息
    retrieved_value_infos: list[ValueInfo]  # 检索到的取值信息

    table_infos: list[TableInfoState]  # 合并和补齐后的表结构上下文
    metric_infos: list[MetricInfoState]  # 合并后的指标上下文
    date_info: DateInfoState  # 当前日期 星期和季度信息
    db_info: DBInfoState  # 数据库方言和版本信息

    selector_candidates: SelectorCandidatesState  # 大 Schema Selector 候选
    selector_enabled: bool  # 是否超过阈值，需要启动 Selector
    schema_token_count: int  # 候选 Schema 的估算 Token 数
    selector_decision: SelectorDecision  # Selector 严格 JSON 选择结果

    retrieved_cube_measures: list[CubeMember]  # 召回到的 Cube 度量候选
    retrieved_cube_dimensions: list[CubeMember]  # 召回到的 Cube 维度候选
    cube_member_catalog: dict[str, CubeMember]  # 当前同步版本的完整成员目录
    resolved_primary_metric: NotRequired[CubeMember]  # 语义关系解析后的主指标
    resolved_attached_metrics: NotRequired[list[CubeMember]]  # 一跳展开后的附带指标
    metric_query_raw: dict  # 通过严格结构校验的模型原始输出
    metric_query_decision: MetricQueryDecision  # 确定性校验后的指标查询决策
    cube_query: dict  # 可直接发送给 Cube 的查询对象
    query_mode: Literal["metric", "sql"]  # 当前请求最终执行模式
    route_reason: SemanticMissReason | Literal["governed_measure_matched"]

    sql: str  # 兼容旧审计字段，后续执行不得读取
    error: str | None  # 兼容旧状态字段，后续路由不得读取
    raw_sql: str  # 模型生成或修正后的不可信 SQL
    normalized_sql: str  # AST 校验通过但未加入系统约束的 SQL
    executable_sql: str  # 注入全部系统约束后的唯一可执行 SQL
    sql_validation_error: str | None  # 可修正的稳定错误分类
    sql_correction_attempts: int  # 当前自动修正次数，最多一次
    sql_cost_estimate: dict  # estimated_rows 与 query_cost
    sql_result_stats: dict  # 行数、字节数、截断标记和耗时
