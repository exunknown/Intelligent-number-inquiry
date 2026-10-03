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
_ALLOWED_ATTACHMENT_RELATION_TYPES = {
    "supporting",
    "comparison",
    "efficiency",
    "breakdown",
}
_ALLOWED_JOIN_RELATIONSHIPS = {
    "many_to_one",
    "one_to_many",
    "one_to_one",
    "many_to_many",
}
_ALLOWED_DIMENSION_TYPES = {"string", "number", "time"}
_ALLOWED_FUNCTIONS = {"NULLIF"}
_ALLOWED_TIME_TYPES = {"date", "datetime", "timestamp"}
_ALLOWED_EXPRESSION_NODES = (
    exp.Add,
    exp.Column,
    exp.Div,
    exp.Identifier,
    exp.Literal,
    exp.Mod,
    exp.Mul,
    exp.Neg,
    exp.Nullif,
    exp.Paren,
    exp.Struct,
    exp.Sub,
)
_MEMBER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_MEMBER_ID_REFERENCE_PATTERN = re.compile(r"^[^:]+:[^:]+:[^:]+$")
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
        issues.extend(self._validate_metric_relations(snapshot))
        issues.extend(self._validate_cubes_and_joins(snapshot))
        issues.extend(self._validate_dependency_graph(snapshot))
        return issues

    @staticmethod
    def _validate_metric_relations(
        snapshot: SemanticModelSnapshot,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        members_by_id = {
            member.member_id: member
            for member in snapshot.members
            if member.release_version == snapshot.release_version
        }
        group_memberships: dict[str, tuple[int, int]] = {}
        group_ids: dict[str, int] = {}

        for group_index, group in enumerate(snapshot.metric_equivalence_groups):
            group_path = f"metric_equivalence_groups[{group_index}]"
            if group.group_id in group_ids:
                issues.append(
                    ValidationIssue(
                        "metric_equivalence_duplicate_group",
                        f"{group_path}.group_id",
                        f"等效指标组 ID 重复：{group.group_id}",
                    )
                )
            else:
                group_ids[group.group_id] = group_index

            canonical_member = members_by_id.get(group.canonical_member_id)
            if canonical_member is None:
                issues.append(
                    ValidationIssue(
                        "metric_equivalence_member_not_found",
                        f"{group_path}.canonical_member_id",
                        f"等效指标标准成员不存在：{group.canonical_member_id}",
                    )
                )
            elif canonical_member.member_type != "measure":
                issues.append(
                    ValidationIssue(
                        "metric_equivalence_member_not_measure",
                        f"{group_path}.canonical_member_id",
                        "等效指标标准成员必须是 measure",
                    )
                )

            canonical_count = 0
            for member_index, group_member in enumerate(group.members):
                member_path = f"{group_path}.members[{member_index}]"
                member = members_by_id.get(group_member.member_id)
                if member is None:
                    issues.append(
                        ValidationIssue(
                            "metric_equivalence_member_not_found",
                            member_path,
                            f"等效指标成员不存在：{group_member.member_id}",
                        )
                    )
                elif member.member_type != "measure":
                    issues.append(
                        ValidationIssue(
                            "metric_equivalence_member_not_measure",
                            member_path,
                            "等效指标组成员必须是 measure",
                        )
                    )
                if group_member.member_id == group.canonical_member_id:
                    canonical_count += 1

                previous = group_memberships.get(group_member.member_id)
                if previous is not None:
                    issues.append(
                        ValidationIssue(
                            "metric_equivalence_duplicate_group",
                            member_path,
                            "一个指标不能重复加入等效指标组",
                        )
                    )
                else:
                    group_memberships[group_member.member_id] = (
                        group_index,
                        member_index,
                    )

            if canonical_count != 1:
                issues.append(
                    ValidationIssue(
                        "metric_equivalence_multiple_canonical",
                        f"{group_path}.canonical_member_id",
                        "等效指标组必须恰好包含一个标准成员",
                    )
                )

        attachment_edges: dict[str, list[str]] = defaultdict(list)
        attachment_pairs: set[tuple[str, str]] = set()
        for attachment_index, attachment in enumerate(snapshot.metric_attachments):
            attachment_path = f"metric_attachments[{attachment_index}]"
            primary_path = f"{attachment_path}.primary_member_id"
            attached_path = f"{attachment_path}.attached_member_id"
            primary_member = members_by_id.get(attachment.primary_member_id)
            attached_member = members_by_id.get(attachment.attached_member_id)

            if primary_member is None:
                issues.append(
                    ValidationIssue(
                        "metric_attachment_member_not_found",
                        primary_path,
                        f"附带指标主成员不存在：{attachment.primary_member_id}",
                    )
                )
            elif primary_member.member_type != "measure":
                issues.append(
                    ValidationIssue(
                        "metric_attachment_member_not_measure",
                        primary_path,
                        "附带指标主成员必须是 measure",
                    )
                )
            if attached_member is None:
                issues.append(
                    ValidationIssue(
                        "metric_attachment_member_not_found",
                        attached_path,
                        f"附带指标成员不存在：{attachment.attached_member_id}",
                    )
                )
            elif attached_member.member_type != "measure":
                issues.append(
                    ValidationIssue(
                        "metric_attachment_member_not_measure",
                        attached_path,
                        "附带指标成员必须是 measure",
                    )
                )
            if attachment.primary_member_id == attachment.attached_member_id:
                issues.append(
                    ValidationIssue(
                        "metric_attachment_self_reference",
                        attached_path,
                        "附带指标不能引用自身",
                    )
                )
            if attachment.relation_type not in _ALLOWED_ATTACHMENT_RELATION_TYPES:
                issues.append(
                    ValidationIssue(
                        "metric_attachment_invalid_relation_type",
                        f"{attachment_path}.relation_type",
                        "附带指标关系类型不在允许范围内",
                    )
                )

            pair = (
                attachment.primary_member_id,
                attachment.attached_member_id,
            )
            if pair in attachment_pairs:
                issues.append(
                    ValidationIssue(
                        "metric_attachment_duplicate",
                        attachment_path,
                        "附带指标关系不能重复",
                    )
                )
            else:
                attachment_pairs.add(pair)

            if (
                primary_member is not None
                and primary_member.member_type == "measure"
                and attached_member is not None
                and attached_member.member_type == "measure"
                and attachment.primary_member_id != attachment.attached_member_id
            ):
                attachment_edges[attachment.primary_member_id].append(
                    attachment.attached_member_id
                )

        cycle_reported = False

        def reaches(start: str, target: str, visited: set[str]) -> bool:
            if start == target:
                return True
            if start in visited:
                return False
            visited.add(start)
            return any(
                reaches(next_member, target, visited)
                for next_member in attachment_edges.get(start, ())
            )

        for attachment_index, attachment in enumerate(snapshot.metric_attachments):
            if cycle_reported:
                break
            if reaches(
                attachment.attached_member_id,
                attachment.primary_member_id,
                set(),
            ):
                issues.append(
                    ValidationIssue(
                        "metric_attachment_cycle",
                        f"metric_attachments[{attachment_index}]",
                        "附带指标关系不能形成循环",
                    )
                )
                cycle_reported = True

        return issues

    def _validate_members(
        self,
        snapshot: SemanticModelSnapshot,
        physical_column_ids: set[str] | None,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        names: dict[tuple[str, str], list[int]] = defaultdict(list)
        members_by_name = {member.qualified_name: member for member in snapshot.members}
        members_by_id = {member.member_id: member for member in snapshot.members}
        cube_names = {cube.cube_name for cube in snapshot.cubes}
        for index, member in enumerate(snapshot.members):
            names[(member.cube_name, member.member_name)].append(index)
            path = f"members[{index}]"
            if not member.member_name:
                issues.append(
                    ValidationIssue(
                        "member_name_required",
                        f"{path}.member_name",
                        "成员名称不能为空",
                    )
                )
            elif _MEMBER_NAME_PATTERN.fullmatch(member.member_name) is None:
                issues.append(
                    ValidationIssue(
                        "invalid_member_name",
                        f"{path}.member_name",
                        "成员名称只能包含字母、数字和下划线",
                    )
                )
            expected_member_id = (
                f"{member.member_type}:{member.cube_name}:{member.member_name}"
            )
            if member.member_id != expected_member_id:
                issues.append(
                    ValidationIssue(
                        "member_id_mismatch",
                        f"{path}.member_id",
                        "成员 ID 必须与成员类型、Cube 和名称一致",
                    )
                )
            if member.cube_name not in cube_names:
                issues.append(
                    ValidationIssue(
                        "member_cube_not_found",
                        f"{path}.cube_name",
                        f"成员所属 Cube 不存在：{member.cube_name}",
                    )
                )
            if member.member_type not in {"measure", "dimension", "time_dimension"}:
                issues.append(
                    ValidationIssue(
                        "member_type_not_allowed",
                        f"{path}.member_type",
                        "成员类型不在允许范围内",
                    )
                )
            if member.source_column_id is not None:
                source_parts = member.source_column_id.split(".")
                if len(source_parts) != 2 or not all(source_parts):
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
                issues.extend(
                    self._validate_measure(
                        member,
                        path,
                        members_by_name,
                        members_by_id,
                    )
                )
            else:
                issues.extend(self._validate_dimension(member, path))
        for (cube_name, member_name), indexes in names.items():
            if len(indexes) > 1:
                issues.append(
                    ValidationIssue(
                        "duplicate_member_name",
                        f"members[{indexes[0]}].member_name",
                        f"成员名称重复：{cube_name}.{member_name}",
                    )
                )
        return issues

    def _validate_measure(
        self,
        member,
        path: str,
        members_by_name: dict,
        members_by_id: dict,
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
            qualified_dependency = self._resolve_dependency_name(
                member,
                dependency,
                members_by_id,
            )
            if (
                qualified_dependency is None
                or qualified_dependency not in members_by_name
            ):
                issues.append(
                    ValidationIssue(
                        "missing_dependency",
                        f"{path}.measure.dependency_members",
                        f"依赖成员不存在：{qualified_dependency or dependency}",
                    )
                )
        return issues

    @staticmethod
    def _resolve_dependency_name(
        member,
        dependency: str,
        members_by_id: dict,
    ) -> str | None:
        referenced_member = members_by_id.get(dependency)
        if referenced_member is not None:
            return referenced_member.qualified_name
        if _MEMBER_ID_REFERENCE_PATTERN.fullmatch(dependency):
            return None
        if "." in dependency:
            return dependency
        return f"{member.cube_name}.{dependency}"

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
        if not isinstance(parsed, _ALLOWED_EXPRESSION_NODES) or any(
            not isinstance(node, _ALLOWED_EXPRESSION_NODES) for node in parsed.walk()
        ):
            return [
                ValidationIssue(
                    "expression_operator_not_allowed",
                    path,
                    "指标表达式包含不允许的函数、操作符或语法节点",
                )
            ]
        return []

    @staticmethod
    def _validate_cubes_and_joins(
        snapshot: SemanticModelSnapshot,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        cube_names: set[str] = set()
        for index, cube in enumerate(snapshot.cubes):
            cube_path = f"cubes[{index}]"
            if not cube.cube_name.strip():
                issues.append(
                    ValidationIssue(
                        "cube_name_required",
                        f"{cube_path}.cube_name",
                        "Cube 名称不能为空",
                    )
                )
            if cube.cube_name in cube_names:
                issues.append(
                    ValidationIssue(
                        "duplicate_cube_name",
                        f"{cube_path}.cube_name",
                        f"Cube 名称不能重复：{cube.cube_name}",
                    )
                )
            else:
                cube_names.add(cube.cube_name)
            if not cube.public and not cube.sql_table.strip():
                issues.append(
                    ValidationIssue(
                        "cube_sql_table_required",
                        f"{cube_path}.sql_table",
                        "Cube 来源表不能为空",
                    )
                )

        join_pairs: set[tuple[str, str]] = set()
        for index, join in enumerate(snapshot.joins):
            join_path = f"joins[{index}]"
            if join.cube_name not in cube_names:
                issues.append(
                    ValidationIssue(
                        "join_source_cube_not_found",
                        f"{join_path}.cube_name",
                        f"Join 来源 Cube 不存在：{join.cube_name}",
                    )
                )
            if join.target_cube_name not in cube_names:
                issues.append(
                    ValidationIssue(
                        "join_target_cube_not_found",
                        f"{join_path}.target_cube_name",
                        f"Join 目标 Cube 不存在：{join.target_cube_name}",
                    )
                )
            if join.cube_name == join.target_cube_name:
                issues.append(
                    ValidationIssue(
                        "join_self_reference",
                        f"{join_path}.target_cube_name",
                        "Join 来源 Cube 和目标 Cube 不能相同",
                    )
                )
            if not join.sql_expression.strip():
                issues.append(
                    ValidationIssue(
                        "join_expression_required",
                        f"{join_path}.sql_expression",
                        "Join 表达式不能为空",
                    )
                )
            if not join.relationship.strip():
                issues.append(
                    ValidationIssue(
                        "join_relationship_required",
                        f"{join_path}.relationship",
                        "Join 关系类型不能为空",
                    )
                )
            elif join.relationship not in _ALLOWED_JOIN_RELATIONSHIPS:
                issues.append(
                    ValidationIssue(
                        "join_relationship_invalid",
                        f"{join_path}.relationship",
                        "Join 关系类型不在允许范围内",
                    )
                )

            pair = (join.cube_name, join.target_cube_name)
            if pair in join_pairs:
                issues.append(
                    ValidationIssue(
                        "duplicate_join",
                        join_path,
                        "相同来源和目标 Cube 的 Join 不能重复",
                    )
                )
            else:
                join_pairs.add(pair)
        return issues

    @staticmethod
    def _validate_dependency_graph(
        snapshot: SemanticModelSnapshot,
    ) -> list[ValidationIssue]:
        members_by_id = {member.member_id: member for member in snapshot.members}
        graph: dict[str, tuple[str, ...]] = {}
        for member in snapshot.members:
            if member.measure is not None:
                graph[member.qualified_name] = tuple(
                    resolved_dependency
                    for dependency in member.measure.dependency_members
                    if (
                        resolved_dependency
                        := SemanticModelValidator._resolve_dependency_name(
                            member,
                            dependency,
                            members_by_id,
                        )
                    )
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
