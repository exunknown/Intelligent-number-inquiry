"""SQL 安全执行阶段使用的不可变领域对象。"""

from dataclasses import dataclass
from typing import Any, Mapping

from app.entities.auth import PermissionSnapshot


@dataclass(frozen=True)
class SQLPolicyLimits:
    """限制模型 SQL 的文本和 AST 复杂度。"""

    max_sql_bytes: int = 32768
    max_ast_nodes: int = 2000
    max_nesting_depth: int = 12
    max_ctes: int = 16
    max_union_branches: int = 16
    max_rows: int = 500


@dataclass(frozen=True)
class SQLPolicyInput:
    """一次 SQL 策略判定所需的输入。"""

    raw_sql: str
    schema: Mapping[str, frozenset[str]]
    permissions: PermissionSnapshot
    dialect: str = "mysql"


@dataclass(frozen=True)
class SQLPolicyResult:
    """通过安全策略后的 SQL 及其引用摘要。"""

    raw_sql: str
    normalized_sql: str
    executable_sql: str
    referenced_tables: tuple[str, ...]
    referenced_columns: tuple[str, ...]


@dataclass(frozen=True)
class SQLCostEstimate:
    """MySQL 查询计划中的保守成本摘要。"""

    estimated_rows: int
    query_cost: float


@dataclass(frozen=True)
class SQLExecutionResult:
    """受资源预算约束的 SQL 执行结果。"""

    rows: tuple[dict[str, Any], ...]
    row_count: int
    result_bytes: int
    truncated: bool
    duration_ms: int
