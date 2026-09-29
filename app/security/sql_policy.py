"""模型 SQL 的 AST 只读安全边界。"""

import logging
from enum import StrEnum

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.errors import ParseError, TokenError

from app.entities.sql_execution import (
    SQLPolicyInput,
    SQLPolicyLimits,
    SQLPolicyResult,
)

# SQLGlot 遇到不支持的命令时会记录截断后的原始 SQL。安全边界不允许模型
# SQL 进入普通日志，因此在适配层统一吞掉该库日志，只保留项目自己的原因码。
_sqlglot_logger = logging.getLogger("sqlglot")
if not any(
    isinstance(handler, logging.NullHandler) for handler in _sqlglot_logger.handlers
):
    _sqlglot_logger.addHandler(logging.NullHandler())
_sqlglot_logger.propagate = False

__all__ = [
    "SQLPolicyEngine",
    "SQLPolicyInput",
    "SQLPolicyLimits",
    "SQLPolicyReason",
    "SQLPolicyResult",
    "SQLPolicyViolation",
]


class SQLPolicyReason(StrEnum):
    """内部稳定的 SQL 安全拒绝原因。"""

    INVALID_SQL = "invalid_sql"
    MULTIPLE_STATEMENTS = "multiple_statements"
    STATEMENT_NOT_READ_ONLY = "statement_not_read_only"
    FORBIDDEN_CONSTRUCT = "forbidden_construct"
    FORBIDDEN_FUNCTION = "forbidden_function"
    QUERY_TOO_COMPLEX = "query_too_complex"


class SQLPolicyViolation(ValueError):
    """不回显原始 SQL 或解析异常的策略拒绝。"""

    def __init__(self, reason: SQLPolicyReason):
        self.reason = reason
        super().__init__(reason.value)


def _expression_types(*names: str) -> tuple[type[exp.Expression], ...]:
    return tuple(
        expression_type
        for name in names
        if isinstance(
            expression_type := getattr(exp, name, None),
            type,
        )
    )


_FORBIDDEN_EXPRESSION_TYPES = _expression_types(
    "Alter",
    "Command",
    "Commit",
    "Copy",
    "Create",
    "Delete",
    "Drop",
    "Execute",
    "Grant",
    "Insert",
    "Into",
    "LoadData",
    "Lock",
    "Merge",
    "Parameter",
    "Prepare",
    "Replace",
    "Revoke",
    "Rollback",
    "SessionParameter",
    "Transaction",
    "TruncateTable",
    "Update",
    "Use",
)

_ALLOWED_FUNCTION_TYPES = _expression_types(
    "Avg",
    "Cast",
    "Coalesce",
    "Count",
    "Day",
    "Max",
    "Min",
    "Month",
    "Nullif",
    "Quarter",
    "Round",
    "Sum",
    "TimeToStr",
    "TsOrDsToDate",
    "TsOrDsToTimestamp",
    "Year",
)


class SQLPolicyEngine:
    """将不可信 SQL 收敛为可继续做权限校验的只读 AST。"""

    def __init__(self, limits: SQLPolicyLimits | None = None):
        self.limits = limits or SQLPolicyLimits()

    def prepare(self, policy_input: SQLPolicyInput) -> SQLPolicyResult:
        """解析并验证单条只读 MySQL 查询。"""

        self._validate_text(policy_input.raw_sql)
        expression = self._parse_one(policy_input)
        self._validate_read_only(expression)
        self._validate_complexity(expression)
        self._validate_functions(expression)

        normalized_sql = expression.sql(dialect=policy_input.dialect)
        referenced_tables = tuple(
            sorted({table.name for table in expression.find_all(exp.Table)})
        )
        referenced_columns = tuple(
            sorted(
                {
                    column.sql(dialect=policy_input.dialect)
                    for column in expression.find_all(exp.Column)
                }
            )
        )
        return SQLPolicyResult(
            raw_sql=policy_input.raw_sql,
            normalized_sql=normalized_sql,
            executable_sql=normalized_sql,
            referenced_tables=referenced_tables,
            referenced_columns=referenced_columns,
        )

    def _validate_text(self, raw_sql: str) -> None:
        if not raw_sql.strip():
            raise SQLPolicyViolation(SQLPolicyReason.INVALID_SQL)
        if len(raw_sql.encode("utf-8")) > self.limits.max_sql_bytes:
            raise SQLPolicyViolation(SQLPolicyReason.QUERY_TOO_COMPLEX)

    @staticmethod
    def _parse_one(policy_input: SQLPolicyInput) -> exp.Expression:
        try:
            expressions = sqlglot.parse(
                policy_input.raw_sql,
                read=policy_input.dialect,
                error_level=ErrorLevel.RAISE,
            )
        except (ParseError, TokenError, ValueError) as exc:
            raise SQLPolicyViolation(SQLPolicyReason.INVALID_SQL) from exc

        parsed = [expression for expression in expressions if expression is not None]
        if len(parsed) != 1:
            raise SQLPolicyViolation(SQLPolicyReason.MULTIPLE_STATEMENTS)
        return parsed[0]

    @staticmethod
    def _validate_read_only(expression: exp.Expression) -> None:
        if not isinstance(expression, (exp.Select, exp.Union)):
            raise SQLPolicyViolation(SQLPolicyReason.STATEMENT_NOT_READ_ONLY)
        if any(
            isinstance(node, _FORBIDDEN_EXPRESSION_TYPES) for node in expression.walk()
        ):
            raise SQLPolicyViolation(SQLPolicyReason.FORBIDDEN_CONSTRUCT)

    def _validate_complexity(self, expression: exp.Expression) -> None:
        if sum(1 for _ in expression.walk()) > self.limits.max_ast_nodes:
            raise SQLPolicyViolation(SQLPolicyReason.QUERY_TOO_COMPLEX)
        if self._depth(expression) > self.limits.max_nesting_depth:
            raise SQLPolicyViolation(SQLPolicyReason.QUERY_TOO_COMPLEX)
        if sum(1 for _ in expression.find_all(exp.CTE)) > self.limits.max_ctes:
            raise SQLPolicyViolation(SQLPolicyReason.QUERY_TOO_COMPLEX)
        if self._max_union_branches(expression) > self.limits.max_union_branches:
            raise SQLPolicyViolation(SQLPolicyReason.QUERY_TOO_COMPLEX)

    @staticmethod
    def _validate_functions(expression: exp.Expression) -> None:
        for function in expression.find_all(exp.Func):
            if not isinstance(function, _ALLOWED_FUNCTION_TYPES):
                raise SQLPolicyViolation(SQLPolicyReason.FORBIDDEN_FUNCTION)

    @classmethod
    def _depth(cls, expression: exp.Expression) -> int:
        children = tuple(expression.iter_expressions())
        if not children:
            return 1
        return 1 + max(cls._depth(child) for child in children)

    @classmethod
    def _max_union_branches(cls, expression: exp.Expression) -> int:
        counts = [
            cls._union_branches(union) for union in expression.find_all(exp.Union)
        ]
        if isinstance(expression, exp.Union):
            counts.append(cls._union_branches(expression))
        return max(counts, default=1)

    @classmethod
    def _union_branches(cls, expression: exp.Expression) -> int:
        if not isinstance(expression, exp.Union):
            return 1
        return cls._union_branches(expression.this) + cls._union_branches(
            expression.expression
        )
