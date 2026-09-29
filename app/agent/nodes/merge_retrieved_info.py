"""
召回信息合并节点

负责把字段和字段取值召回结果聚合成 SQL 兜底上下文
这一层会补齐字段真实取值 主外键字段和表信息
后续过滤节点不再关心信息来自哪个检索分支，只处理合并后的表上下文和指标上下文
"""

from dataclasses import replace

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import (
    ColumnInfoState,
    DataAgentState,
    SelectorCandidatesState,
    SelectorColumnState,
    SelectorTableState,
    SelectorValueState,
    TableInfoState,
)
from app.core.log import logger
from app.core.resource_governance import await_with_budget
from app.entities.column_info import ColumnInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo
from app.security.resource_filter import filter_columns, filter_tables


async def merge_retrieved_info(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
):
    """合并召回结果，并输出 SQL 生成前的候选表信息和指标信息"""

    writer = runtime.stream_writer
    step = "合并召回信息"
    writer({"type": "progress", "step": step, "status": "running"})

    try:
        retrieved_column_infos: list[ColumnInfo] = state["retrieved_column_infos"]
        retrieved_value_infos: list[ValueInfo] = state["retrieved_value_infos"]

        meta_mysql_repository = runtime.context["meta_mysql_repository"]
        permissions = runtime.context["permissions"]
        resource_budget = runtime.context.get("resource_budget")
        meta_breaker = runtime.context.get("dependency_breakers", {}).get("mysql_meta")

        # 本节点的主线是：
        # 字段召回 + 字段真实取值 + 主外键补齐
        # -> table_infos / metric_infos，交给后续过滤和 SQL 生成节点继续使用。

        # 1. 以 column_id 为 key 合并字段信息
        # 三路召回可能命中同一个字段，用 dict 可以自然去重；
        # 后续字段取值也通过 column_id 合并进来。
        retrieved_column_infos_map: dict[str, ColumnInfo] = {
            retrieved_column_info.id: replace(
                retrieved_column_info, examples=list(retrieved_column_info.examples)
            )
            for retrieved_column_info in retrieved_column_infos
        }

        # 2. 把字段取值合并回字段 examples
        # 字段取值召回命中的是 column_id + value，例如 dim_region.region_name.华北。
        # 把真实 value 放进字段 examples，可以帮助模型写出更接近真实数据的 where 条件。
        for retrieved_value_info in retrieved_value_infos:
            value = retrieved_value_info.value
            column_id = retrieved_value_info.column_id
            if column_id not in retrieved_column_infos_map:
                column_info: ColumnInfo = await await_with_budget(
                    meta_mysql_repository.get_column_info_by_id(column_id),
                    resource_budget,
                    circuit_breaker=meta_breaker,
                    dependency="mysql_meta",
                )
                allowed = filter_columns([column_info], permissions)
                if not allowed:
                    continue
                retrieved_column_infos_map[column_id] = replace(
                    allowed[0], examples=list(allowed[0].examples)
                )
            if value not in retrieved_column_infos_map[column_id].examples:
                retrieved_column_infos_map[column_id].examples.append(value)

        # 3. 按表组织字段上下文
        # SQL 生成提示词通常按“表 -> 字段列表”的方式描述结构，
        # 所以这里先把分散的字段按 table_id 归到各自所属表下面。
        table_to_columns_map: dict[str, list[ColumnInfo]] = {}
        for column_info in retrieved_column_infos_map.values():
            table_id = column_info.table_id
            if table_id not in permissions.allowed_tables:
                continue
            if table_id not in table_to_columns_map:
                table_to_columns_map[table_id] = []
            table_to_columns_map[table_id].append(column_info)

        # 4. 补齐主外键字段
        # 主外键通常不会出现在用户问题里，单靠向量召回容易漏掉；
        # 但多表查询的 Join 路径必须依赖它们，所以每张候选表都要兜底补齐。
        for table_id in table_to_columns_map.keys():
            key_columns: list[ColumnInfo] = await await_with_budget(
                meta_mysql_repository.get_key_columns_by_table_id(table_id),
                resource_budget,
                circuit_breaker=meta_breaker,
                dependency="mysql_meta",
            )
            column_ids = [
                column_info.id for column_info in table_to_columns_map[table_id]
            ]
            for key_column in key_columns:
                if (
                    key_column.id not in column_ids
                    and key_column.id in permissions.allowed_columns
                ):
                    table_to_columns_map[table_id].append(
                        replace(key_column, examples=list(key_column.examples))
                    )

        # 5. 生成表结构上下文
        # 数据库实体里可能包含入库和索引用字段，传给模型前只保留必要信息，
        # 让后续过滤和 SQL 生成节点面对的是更稳定的 TableInfoState 结构。
        table_infos: list[TableInfoState] = []
        selector_tables: list[SelectorTableState] = []
        for table_id, column_infos in table_to_columns_map.items():
            table_info: TableInfo = await await_with_budget(
                meta_mysql_repository.get_table_info_by_id(table_id),
                resource_budget,
                circuit_breaker=meta_breaker,
                dependency="mysql_meta",
            )
            if not filter_tables([table_info], permissions):
                continue
            columns = [
                ColumnInfoState(
                    name=column_info.name,
                    type=column_info.type,
                    role=column_info.role,
                    examples=list(column_info.examples),
                    description=column_info.description,
                    alias=column_info.alias,
                )
                for column_info in column_infos
            ]
            table_info_state = TableInfoState(
                name=table_info.name,
                role=table_info.role,
                description=table_info.description,
                columns=columns,
            )
            table_infos.append(table_info_state)

            selector_columns: list[SelectorColumnState] = [
                SelectorColumnState(
                    id=column_info.id,
                    table_id=column_info.table_id,
                    name=column_info.name,
                    type=column_info.type,
                    role=column_info.role,
                    examples=list(column_info.examples),
                    description=column_info.description,
                    alias=column_info.alias,
                )
                for column_info in column_infos
            ]
            selector_tables.append(
                SelectorTableState(
                    id=table_info.id,
                    name=table_info.name,
                    role=table_info.role,
                    description=table_info.description,
                    columns=selector_columns,
                )
            )

        # 6. SQL 兜底不再消费旧指标元数据，指标语义只来自 Cube 受治理成员。
        metric_infos = []
        selector_values: list[SelectorValueState] = [
            SelectorValueState(
                id=retrieved_value_info.id,
                value=retrieved_value_info.value,
                column_id=retrieved_value_info.column_id,
            )
            for retrieved_value_info in retrieved_value_infos
        ]
        selector_candidates = SelectorCandidatesState(
            tables=selector_tables,
            metrics=[],
            values=selector_values,
        )

        logger.info(
            f"合并后的表信息：{[table_info['name'] for table_info in table_infos]}"
        )
        logger.info(
            f"合并后的指标信息：{[metric_info['name'] for metric_info in metric_infos]}"
        )

        writer({"type": "progress", "step": step, "status": "success"})
        return {
            "table_infos": table_infos,
            "metric_infos": metric_infos,
            "selector_candidates": selector_candidates,
        }
    except Exception as e:
        logger.error(f"{step} failed: {e}")
        writer({"type": "progress", "step": step, "status": "error"})
        raise
