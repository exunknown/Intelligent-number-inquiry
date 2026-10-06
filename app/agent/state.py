"""
电商问数 Agent 状态定义

State 是 LangGraph 各节点之间传递和更新的共享数据
本章在用户原始问题之外，新增关键词列表和三路召回结果
并把召回到的实体整理成后续提示词更容易消费的表信息和指标信息
SQL 生成闭环会继续写入候选 SQL 以及校验错误信息，用于控制校正或执行分支
"""

from dataclasses import asdict, is_dataclass
from typing import Any, Literal, NotRequired, TypedDict

import sqlglot
from sqlglot import exp

from app.agent.selector import SelectorDecision
from app.entities.column_info import ColumnInfo
from app.entities.cube_member import CubeMember
from app.entities.knowledge_graph import (
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    KnowledgeGraphPath,
)
from app.entities.metric_info import MetricInfo
from app.entities.metric_query import MetricQueryDecision, SemanticMissReason
from app.entities.query_turn_context import QueryTurnContext
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
    original_query: NotRequired[str]  # 用户原始问题，供多轮解析失败时回退
    effective_query: NotRequired[str]  # 会话解析后的完整问题
    recent_turn_contexts: NotRequired[list[QueryTurnContext]]  # 当前会话最近上下文
    conversation_mode: NotRequired[Literal["standalone", "follow_up", "clarification"]]
    inherited_from_context_id: NotRequired[str | None]
    conversation_reason: NotRequired[str]
    keywords: list[str]  # 抽取的关键词
    retrieved_column_infos: list[ColumnInfo]  # 检索到的字段信息
    retrieved_metric_infos: list[MetricInfo]  # 检索到的指标信息
    retrieved_value_infos: list[ValueInfo]  # 检索到的取值信息
    retrieved_graph_nodes: NotRequired[list[KnowledgeGraphNode]]
    retrieved_graph_edges: NotRequired[list[KnowledgeGraphEdge]]
    graph_paths: NotRequired[list[KnowledgeGraphPath]]
    graph_evidence_summary: NotRequired[dict[str, object]]
    graph_evidence: NotRequired[dict[str, object]]

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
    resolved_primary_metrics: NotRequired[list[CubeMember]]  # 最终顺序的全部主指标
    resolved_attached_metrics: NotRequired[list[CubeMember]]  # 一跳展开后的附带指标
    resolved_attached_metric_sources: NotRequired[
        dict[str, str]
    ]  # 附带指标的主指标来源
    resolved_compatibility_notes: NotRequired[dict[str, str]]  # 主指标兼容口径说明
    include_attached_metrics: bool  # 是否展开默认展示的一跳附带指标
    metric_query_raw: dict  # 通过严格结构校验的模型原始输出
    metric_query_decision: MetricQueryDecision  # 确定性校验后的指标查询决策
    metric_result_cacheable: bool  # 当前指标查询结果是否允许写入短 TTL 缓存
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


def build_graph_evidence(
    state: DataAgentState,
    *,
    allowed_edge_types: set[str] | frozenset[str] | None = None,
    allowed_node_types: set[str] | frozenset[str] | None = None,
    max_nodes: int = 40,
    max_edges: int = 40,
    max_paths: int = 20,
) -> dict[str, object]:
    """把图谱实体投影为可进入后续上下文的最小安全证据。"""

    raw_nodes = [
        node
        for node in state.get("retrieved_graph_nodes", [])
        if isinstance(node, KnowledgeGraphNode)
        and (allowed_node_types is None or node.node_type in allowed_node_types)
    ]
    node_by_id = {node.node_id: node for node in raw_nodes}
    raw_edges = [
        edge
        for edge in state.get("retrieved_graph_edges", [])
        if isinstance(edge, KnowledgeGraphEdge)
        and (allowed_edge_types is None or edge.edge_type in allowed_edge_types)
        and edge.source_node_id in node_by_id
        and edge.target_node_id in node_by_id
    ]
    raw_edges.sort(key=lambda edge: edge.edge_id)
    raw_edges = raw_edges[: max(0, max_edges)]
    related_node_ids = {
        node_id
        for edge in raw_edges
        for node_id in (edge.source_node_id, edge.target_node_id)
    }
    selected_nodes = [
        node for node in raw_nodes if not raw_edges or node.node_id in related_node_ids
    ]
    selected_nodes.sort(key=lambda node: node.node_id)
    selected_nodes = selected_nodes[: max(0, max_nodes)]
    selected_node_ids = {node.node_id for node in selected_nodes}
    selected_edge_ids = {
        edge.edge_id
        for edge in raw_edges
        if (
            edge.source_node_id in selected_node_ids
            and edge.target_node_id in selected_node_ids
        )
    }

    edges: list[dict[str, object]] = []
    for edge in raw_edges:
        if edge.edge_id not in selected_edge_ids:
            continue
        note = None
        for key in ("relationship", "relation_type", "note"):
            value = edge.evidence.get(key)
            if isinstance(value, str) and value.strip():
                note = value.strip()[:80]
                break
        item: dict[str, object] = {
            "id": edge.edge_id,
            "type": edge.edge_type,
            "source": edge.source_node_id,
            "target": edge.target_node_id,
        }
        if note is not None:
            item["note"] = note
        edges.append(item)

    edge_id_set = {item["id"] for item in edges}
    paths: list[dict[str, object]] = []
    for path in state.get("graph_paths", []):
        if not isinstance(path, KnowledgeGraphPath):
            continue
        if not set(path.edge_ids).issubset(edge_id_set):
            continue
        if not set(path.node_ids).issubset(selected_node_ids):
            continue
        paths.append(path.to_dict())
        if len(paths) >= max(0, max_paths):
            break

    return {
        "nodes": [
            {"id": node.node_id, "type": node.node_type} for node in selected_nodes
        ],
        "edges": edges,
        "paths": paths,
    }


def _safe_context_value(value: Any) -> Any:
    """把上下文投影为可持久化的业务标量、列表和对象。"""

    if is_dataclass(value):
        return _safe_context_value(asdict(value))
    if isinstance(value, dict):
        return {
            str(key): _safe_context_value(item)
            for key, item in value.items()
            if str(key).strip().lower()
            not in {
                "data",
                "executable_sql",
                "authorization",
                "connection",
                "connection_info",
                "connection_string",
                "database",
                "database_url",
                "db",
                "db_host",
                "db_url",
                "dsn",
                "full_result",
                "host",
                "hostname",
                "normalized_sql",
                "password",
                "prompt",
                "raw_sql",
                "raw_result",
                "records",
                "result",
                "result_rows",
                "rows",
                "secret",
                "sql",
                "token",
            }
        }
    if isinstance(value, (list, tuple)):
        return [_safe_context_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def _metric_turn_context(state: DataAgentState) -> dict[str, object]:
    decision = state.get("metric_query_decision")
    query = getattr(decision, "query", None)
    if query is None:
        return {}
    return _safe_context_value(query)


def _sql_turn_context(state: DataAgentState) -> dict[str, object]:
    tables: list[str] = []
    columns: list[str] = []
    for table in state.get("table_infos", []):
        if not isinstance(table, dict) or not isinstance(table.get("name"), str):
            continue
        table_name = table["name"]
        tables.append(table_name)
        for column in table.get("columns", []):
            if isinstance(column, dict) and isinstance(column.get("name"), str):
                columns.append(f"{table_name}.{column['name']}")

    candidates = state.get("selector_candidates") or {}
    column_names = {
        column["id"]: f"{table['name']}.{column['name']}"
        for table in candidates.get("tables", [])
        if isinstance(table, dict) and isinstance(table.get("name"), str)
        for column in table.get("columns", [])
        if isinstance(column, dict)
        and isinstance(column.get("id"), str)
        and isinstance(column.get("name"), str)
    }
    values_by_id = {
        item["id"]: item
        for item in candidates.get("values", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    selector_decision = state.get("selector_decision") or {}
    selected_values = (
        selector_decision.get("keep_values", [])
        if isinstance(selector_decision, dict)
        else []
    )
    filters: list[dict[str, object]] = []
    for selected in selected_values:
        if not isinstance(selected, dict):
            continue
        value_id = selected.get("value_id")
        selected_column_id = selected.get("column_id")
        item = values_by_id.get(value_id)
        if item is None:
            continue
        value = item.get("value")
        column_id = selected_column_id or item.get("column_id")
        if isinstance(column_id, str) and isinstance(value, (str, int, float, bool)):
            filters.append(
                {
                    "column": column_names.get(column_id, column_id),
                    "value": value,
                }
            )

    context: dict[str, object] = {
        "tables": tables,
        "columns": columns,
        "filters": filters,
    }
    context.update(_sql_shape_summary(state.get("normalized_sql")))
    for key in ("group_by", "order_by", "limit"):
        value = state.get(f"sql_{key}") or state.get(key)
        if value is not None:
            context[key] = _safe_context_value(value)
    return context


def _sql_expression_summary(expression: exp.Expression) -> str | None:
    """把已通过 SQL 策略校验的单个表达式压缩为结构摘要。"""

    try:
        summary = expression.sql(dialect="mysql").strip()
    except Exception:
        return None
    if not summary or len(summary) > 128:
        return None
    return summary


def _sql_shape_summary(normalized_sql: object) -> dict[str, object]:
    """从策略校验后的 SQL 中提取分组、排序和条数摘要，不保存 SQL 原文。"""

    if not isinstance(normalized_sql, str) or not normalized_sql.strip():
        return {}
    try:
        expression = sqlglot.parse_one(normalized_sql, read="mysql")
    except (sqlglot.ParseError, sqlglot.TokenError, ValueError):
        return {}

    query = expression
    if isinstance(expression, exp.Union):
        query = expression.this
    if not isinstance(query, exp.Select):
        return {}

    summary: dict[str, object] = {}
    group = query.args.get("group")
    if group is not None:
        group_by = [
            item_summary
            for item in group.expressions
            if (item_summary := _sql_expression_summary(item)) is not None
        ]
        if group_by:
            summary["group_by"] = group_by

    order = query.args.get("order")
    if order is not None:
        order_by: list[dict[str, str]] = []
        for item in order.expressions:
            expression_summary = _sql_expression_summary(item.this)
            if expression_summary is None:
                continue
            order_by.append(
                {
                    "expression": expression_summary,
                    "direction": "desc" if item.args.get("desc") else "asc",
                }
            )
        if order_by:
            summary["order_by"] = order_by

    limit = query.args.get("limit")
    limit_expression = limit.args.get("expression") if limit is not None else None
    if isinstance(limit_expression, exp.Literal) and not limit_expression.is_string:
        try:
            limit_value = int(limit_expression.this)
        except (TypeError, ValueError):
            limit_value = None
        if limit_value is not None and limit_value >= 0:
            summary["limit"] = limit_value
    return summary


def build_turn_context_payload(
    state: DataAgentState, result_summary: dict[str, object] | None
) -> dict[str, object]:
    """构造不含 SQL 和原始结果的内部轮次上下文事件。"""

    query_mode = state.get("query_mode")
    if query_mode not in {"metric", "sql"}:
        query_mode = "sql" if state.get("raw_sql") else "metric"
    context = (
        _metric_turn_context(state)
        if query_mode == "metric"
        else _sql_turn_context(state)
    )
    return {
        "effective_query": state.get("effective_query") or state.get("query", ""),
        "query_mode": query_mode,
        "context": context,
        "result_summary": _safe_context_value(result_summary),
        "metadata_release_version": state.get("metadata_release_version"),
        "inherited_from_context_id": state.get("inherited_from_context_id"),
    }
