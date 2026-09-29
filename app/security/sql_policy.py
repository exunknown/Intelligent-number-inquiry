"""模型 SQL 的 AST 只读安全边界。"""

import logging
from enum import StrEnum

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.errors import OptimizeError, ParseError, TokenError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

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
    SCHEMA_NOT_ALLOWED = "schema_not_allowed"
    TABLE_NOT_SUPPORTED = "table_not_supported"
    TABLE_NOT_ALLOWED = "table_not_allowed"
    COLUMN_NOT_ALLOWED = "column_not_allowed"
    IDENTIFIER_UNRESOLVED = "identifier_unresolved"
    WILDCARD_NOT_ALLOWED = "wildcard_not_allowed"
    NO_DATA_SCOPE = "no_data_scope"


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
    "Exists",
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
        self._validate_wildcards(expression)
        expression, referenced_tables, referenced_columns = self._authorize_scope(
            expression, policy_input
        )

        normalized_sql = expression.sql(dialect=policy_input.dialect)
        executable_expression = self._inject_department_scope(
            expression.copy(), policy_input
        )
        executable_expression = self._wrap_with_row_limit(executable_expression)
        return SQLPolicyResult(
            raw_sql=policy_input.raw_sql,
            normalized_sql=normalized_sql,
            executable_sql=executable_expression.sql(dialect=policy_input.dialect),
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
            # SQLGlot 的 AND/OR 节点也继承 Func，但它们是语法连接器，
            # 不应按可调用数据库函数参与白名单判断。
            if isinstance(function, exp.Connector):
                continue
            if not isinstance(function, _ALLOWED_FUNCTION_TYPES):
                raise SQLPolicyViolation(SQLPolicyReason.FORBIDDEN_FUNCTION)

    @staticmethod
    def _validate_wildcards(expression: exp.Expression) -> None:
        for star in expression.find_all(exp.Star):
            if not isinstance(star.parent, exp.Count):
                raise SQLPolicyViolation(SQLPolicyReason.WILDCARD_NOT_ALLOWED)

    @classmethod
    def _authorize_scope(
        cls,
        expression: exp.Expression,
        policy_input: SQLPolicyInput,
    ) -> tuple[exp.Expression, tuple[str, ...], tuple[str, ...]]:
        supported_schema = {
            table.casefold(): {column.casefold(): "UNKNOWN" for column in columns}
            for table, columns in policy_input.schema.items()
        }
        physical_tables = cls._physical_tables(expression)
        referenced_tables: set[str] = set()

        for table in physical_tables:
            if table.catalog or (table.db and table.db.casefold() != "dw"):
                raise SQLPolicyViolation(SQLPolicyReason.SCHEMA_NOT_ALLOWED)

            table_name = table.name.casefold()
            if table_name not in supported_schema:
                raise SQLPolicyViolation(SQLPolicyReason.TABLE_NOT_SUPPORTED)
            if table_name not in policy_input.permissions.allowed_tables:
                raise SQLPolicyViolation(SQLPolicyReason.TABLE_NOT_ALLOWED)

            referenced_tables.add(table_name)
            table.set("catalog", None)
            table.set("db", None)

        try:
            qualified = qualify(
                expression,
                dialect=policy_input.dialect,
                schema=supported_schema,
                expand_stars=False,
                infer_schema=False,
                allow_partial_qualification=False,
                validate_qualify_columns=True,
                quote_identifiers=False,
                identify=False,
            )
        except OptimizeError as exc:
            raise SQLPolicyViolation(SQLPolicyReason.IDENTIFIER_UNRESOLVED) from exc

        referenced_columns: set[str] = set()
        for scope in traverse_scope(qualified):
            for column in scope.columns:
                source = cls._resolve_source(scope, column.table)
                if isinstance(source, Scope):
                    continue
                if not isinstance(source, exp.Table):
                    raise SQLPolicyViolation(SQLPolicyReason.IDENTIFIER_UNRESOLVED)

                table_name = source.name.casefold()
                column_name = column.name.casefold()
                column_id = f"{table_name}.{column_name}"
                if column_name not in supported_schema.get(table_name, {}):
                    raise SQLPolicyViolation(SQLPolicyReason.IDENTIFIER_UNRESOLVED)
                if column_id not in policy_input.permissions.allowed_columns:
                    raise SQLPolicyViolation(SQLPolicyReason.COLUMN_NOT_ALLOWED)
                referenced_columns.add(column_id)

        return (
            qualified,
            tuple(sorted(referenced_tables)),
            tuple(sorted(referenced_columns)),
        )

    @staticmethod
    def _physical_tables(expression: exp.Expression) -> tuple[exp.Table, ...]:
        tables: dict[int, exp.Table] = {}
        for scope in traverse_scope(expression):
            for source in scope.sources.values():
                if isinstance(source, exp.Table):
                    tables[id(source)] = source
        return tuple(tables.values())

    @staticmethod
    def _resolve_source(scope: Scope, alias: str) -> exp.Table | Scope | None:
        current: Scope | None = scope
        while current is not None:
            source = current.sources.get(alias)
            if source is not None:
                return source
            current = current.parent
        return None

    def _inject_department_scope(
        self,
        expression: exp.Expression,
        policy_input: SQLPolicyInput,
    ) -> exp.Expression:
        department_ids = tuple(sorted(policy_input.permissions.allowed_department_ids))
        if not department_ids:
            raise SQLPolicyViolation(SQLPolicyReason.NO_DATA_SCOPE)

        fact_columns = {
            column.casefold()
            for column in policy_input.schema.get("fact_order", frozenset())
        }
        for scope in traverse_scope(expression):
            if not isinstance(scope.expression, exp.Select):
                continue
            aliases = sorted(
                alias
                for alias, source in scope.sources.items()
                if isinstance(source, exp.Table)
                and source.name.casefold() == "fact_order"
            )
            if not aliases:
                continue
            if "department_id" not in fact_columns:
                raise SQLPolicyViolation(SQLPolicyReason.IDENTIFIER_UNRESOLVED)

            predicate: exp.Expression | None = None
            for alias in aliases:
                alias_predicate = exp.In(
                    this=exp.column("department_id", table=alias),
                    expressions=[
                        exp.Literal.string(department_id)
                        for department_id in department_ids
                    ],
                )
                predicate = (
                    alias_predicate
                    if predicate is None
                    else exp.and_(predicate, alias_predicate)
                )

            existing_where = scope.expression.args.get("where")
            if existing_where is not None:
                predicate = exp.and_(existing_where.this.copy(), predicate)
            scope.expression.set("where", exp.Where(this=predicate))

        return expression

    def _wrap_with_row_limit(self, expression: exp.Expression) -> exp.Select:
        if self.limits.max_rows < 1:
            raise SQLPolicyViolation(SQLPolicyReason.QUERY_TOO_COMPLEX)
        subquery = exp.Subquery(
            this=expression,
            alias=exp.TableAlias(this=exp.to_identifier("_authorized_query")),
        )
        return exp.select("*").from_(subquery).limit(self.limits.max_rows + 1)

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
