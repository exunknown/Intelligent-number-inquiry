"""语义模型发布前的确定性校验。"""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from app.entities.semantic_model import SemanticModelSnapshot

IssueSeverity = Literal["error", "warning"]

_ALLOWED_AGGREGATIONS = {"sum", "count", "count_distinct", "number"}
_ALLOWED_DIMENSION_TYPES = {"string", "number", "time"}
_ALLOWED_FUNCTIONS = {"NULLIF"}
_ALLOWED_TIME_TYPES = {"date", "datetime", "timestamp"}
_FUNCTION_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_FORBIDDEN_SQL_PATTERN = re.compile(
    r"(?:;|--|/\*|\*/|\b(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationIssue:
    """一个稳定、可直接展示给治理页面的校验问题。"""

    code: str
    path: str
    message: str
    severity: IssueSeverity = "error"


class SemanticModelValidator:
    """只执行语法和结构校验，不执行任何用户表达式。"""

    def validate(
        self,
        snapshot: SemanticModelSnapshot,
        physical_column_ids: set[str] | None = None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        issues.extend(self._validate_members(snapshot, physical_column_ids))
        issues.extend(self._validate_cubes_and_joins(snapshot))
        issues.extend(self._validate_dependency_graph(snapshot))
        return issues

    def _validate_members(
        self,
        snapshot: SemanticModelSnapshot,
        physical_column_ids: set[str] | None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        names: dict[str, list[int]] = defaultdict(list)
        members_by_name = {member.qualified_name: member for member in snapshot.members}
        for index, member in enumerate(snapshot.members):
            names[member.qualified_name].append(index)
            path = f"members[{index}]"
            if member.member_type not in {"measure", "dimension", "time_dimension"}:
                issues.append(
                    ValidationIssue(
                        "member_type_not_allowed",
                        f"{path}.member_type",
                        "成员类型不在允许范围内",
                    )
                )
            if member.source_column_id is not None:
                if member.source_column_id.count(".") != 1:
                    issues.append(
                        ValidationIssue(
                            "invalid_source_column_id",
                            f"{path}.source_column_id",
                            "来源字段必须使用 table.column 格式",
                        )
                    )
                elif (
                    physical_column_ids is not None
                    and member.source_column_id not in physical_column_ids
                ):
                    issues.append(
                        ValidationIssue(
                            "source_column_not_found",
                            f"{path}.source_column_id",
                            "来源字段不存在于物理字段目录",
                        )
                    )
            if member.member_type == "measure":
                issues.extend(self._validate_measure(member, path, members_by_name))
            else:
                issues.extend(self._validate_dimension(member, path))
        for qualified_name, indexes in names.items():
            if len(indexes) > 1:
                issues.append(
                    ValidationIssue(
                        "duplicate_member_name",
                        f"members[{indexes[0]}].member_name",
                        f"成员名称重复：{qualified_name}",
                    )
                )
        return issues

    def _validate_measure(
        self,
        member,
        path: str,
        members_by_name: dict,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        definition = member.measure
        if definition is None:
            return issues
        if definition.aggregation_type not in _ALLOWED_AGGREGATIONS:
            issues.append(
                ValidationIssue(
                    "aggregation_type_not_allowed",
                    f"{path}.measure.aggregation_type",
                    "指标聚合类型不在允许范围内",
                )
            )
        issues.extend(
            self._validate_expression(
                definition.expression, f"{path}.measure.expression"
            )
        )
        for dependency in definition.dependency_members:
            qualified_dependency = (
                dependency if "." in dependency else f"{member.cube_name}.{dependency}"
            )
            if qualified_dependency not in members_by_name:
                issues.append(
                    ValidationIssue(
                        "missing_dependency",
                        f"{path}.measure.dependency_members",
                        f"依赖成员不存在：{qualified_dependency}",
                    )
                )
        return issues

    def _validate_dimension(self, member, path: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        definition = member.dimension
        if definition is None:
            return issues
        if definition.dimension_type not in _ALLOWED_DIMENSION_TYPES:
            issues.append(
                ValidationIssue(
                    "dimension_type_not_allowed",
                    f"{path}.dimension.dimension_type",
                    "维度类型不在允许范围内",
                )
            )
        if member.member_type == "time_dimension":
            if (
                definition.dimension_type != "time"
                or member.data_type not in _ALLOWED_TIME_TYPES
            ):
                issues.append(
                    ValidationIssue(
                        "time_dimension_type_mismatch",
                        f"{path}.dimension",
                        "时间维度必须使用 time 类型和日期数据类型",
                    )
                )
            if not definition.time_granularity:
                issues.append(
                    ValidationIssue(
                        "time_granularity_required",
                        f"{path}.dimension.time_granularity",
                        "时间维度必须指定时间粒度",
                    )
                )
        elif definition.time_granularity is not None:
            issues.append(
                ValidationIssue(
                    "time_granularity_not_allowed",
                    f"{path}.dimension.time_granularity",
                    "非时间维度不能指定时间粒度",
                )
            )
        return issues

    @staticmethod
    def _validate_expression(expression: str, path: str) -> list[ValidationIssue]:
        if not expression.strip():
            return [ValidationIssue("expression_required", path, "指标表达式不能为空")]
        if _FORBIDDEN_SQL_PATTERN.search(expression):
            return [
                ValidationIssue(
                    "expression_contains_sql",
                    path,
                    "表达式只能包含受限计算语法",
                )
            ]
        for function_name in _FUNCTION_PATTERN.findall(expression):
            if function_name.upper() not in _ALLOWED_FUNCTIONS:
                return [
                    ValidationIssue(
                        "expression_function_not_allowed",
                        path,
                        f"函数不在白名单内：{function_name}",
                    )
                ]
        normalized = re.sub(r"\{([^{}]+)\}", r"\1", expression)
        try:
            parsed = parse_one(normalized, read="mysql")
        except ParseError:
            return [
                ValidationIssue(
                    "expression_parse_error",
                    path,
                    "指标表达式无法解析",
                )
            ]
        if isinstance(parsed, (exp.Select, exp.Insert, exp.Update, exp.Delete)):
            return [
                ValidationIssue(
                    "expression_statement_not_allowed",
                    path,
                    "指标表达式不能是查询或写入语句",
                )
            ]
        return []

    @staticmethod
    def _validate_cubes_and_joins(
        snapshot: SemanticModelSnapshot,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        cube_names = {cube.cube_name for cube in snapshot.cubes}
        for index, join in enumerate(snapshot.joins):
            if join.cube_name not in cube_names:
                issues.append(
                    ValidationIssue(
                        "join_source_cube_not_found",
                        f"joins[{index}].cube_name",
                        f"Join 来源 Cube 不存在：{join.cube_name}",
                    )
                )
            if join.target_cube_name not in cube_names:
                issues.append(
                    ValidationIssue(
                        "join_target_cube_not_found",
                        f"joins[{index}].target_cube_name",
                        f"Join 目标 Cube 不存在：{join.target_cube_name}",
                    )
                )
        return issues

    @staticmethod
    def _validate_dependency_graph(
        snapshot: SemanticModelSnapshot,
    ) -> list[ValidationIssue]:
        graph: dict[str, tuple[str, ...]] = {}
        for member in snapshot.members:
            if member.measure is not None:
                graph[member.qualified_name] = tuple(
                    dependency
                    if "." in dependency
                    else f"{member.cube_name}.{dependency}"
                    for dependency in member.measure.dependency_members
                )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> bool:
            if name in visiting:
                return True
            if name in visited:
                return False
            visiting.add(name)
            has_cycle = any(
                dependency in graph and visit(dependency)
                for dependency in graph.get(name, ())
            )
            visiting.remove(name)
            visited.add(name)
            return has_cycle

        if any(visit(name) for name in graph):
            return [
                ValidationIssue(
                    "dependency_cycle",
                    "members",
                    "指标依赖关系存在循环",
                )
            ]
        return []
