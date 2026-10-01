"""将已校验的语义模型快照转换为 Cube 运行模型。"""

import re
from collections.abc import Mapping

from sqlglot import exp, parse_one

from app.entities.semantic_model import SemanticMember, SemanticModelSnapshot
from app.services.semantic_model_validation import SemanticModelValidator

_MEMBER_REFERENCE_PATTERN = re.compile(r"\{([^{}]+)\}")


def schema_version(snapshot: SemanticModelSnapshot) -> str:
    """返回与发布快照绑定的 Cube schema version。"""

    return snapshot.release_version


def build_cube_model(snapshot: SemanticModelSnapshot) -> dict[str, object]:
    """构建底层 Cube 和公开 ecommerce view 的模型字典。"""

    _validate_snapshot(snapshot)
    model: dict[str, object] = {}
    for cube in snapshot.cubes:
        model[cube.cube_name] = {
            "sql_table": cube.sql_table,
            "title": cube.title,
            "description": cube.description,
            "public": cube.public,
            "measures": {},
            "dimensions": {},
            "joins": {},
        }

    for join in snapshot.joins:
        cube_model = model.get(join.cube_name)
        if isinstance(cube_model, dict):
            joins = cube_model["joins"]
            if isinstance(joins, dict):
                joins[join.target_cube_name] = {
                    "sql": join.sql_expression,
                    "relationship": join.relationship,
                }

    model["ecommerce"] = build_ecommerce_view(snapshot)
    return model


def build_ecommerce_view(snapshot: SemanticModelSnapshot) -> dict[str, object]:
    """构建公开语义视图，只暴露快照中的受治理成员。"""

    _validate_snapshot(snapshot)
    measures: dict[str, object] = {}
    dimensions: dict[str, object] = {}
    for member in snapshot.members:
        if member.member_type == "measure":
            if member.measure is None:
                raise ValueError(
                    f"measure definition is missing: {member.qualified_name}"
                )
            measure = member.measure
            measures[member.member_name] = {
                "sql": _measure_sql(member),
                "type": measure.aggregation_type,
                "title": member.title,
                "description": member.description,
                "meta": _member_metadata(member),
            }
        else:
            if member.dimension is None:
                raise ValueError(
                    f"dimension definition is missing: {member.qualified_name}"
                )
            dimension = member.dimension
            dimensions[member.member_name] = {
                "sql": _physical_column_sql(member),
                "type": (
                    "time"
                    if member.member_type == "time_dimension"
                    else dimension.dimension_type
                ),
                "title": member.title,
                "description": member.description,
                "meta": _member_metadata(member),
            }
    return {
        "title": "电商经营分析",
        "description": "已治理的电商订单指标与分析维度",
        "public": True,
        "measures": measures,
        "dimensions": dimensions,
    }


def _validate_snapshot(snapshot: SemanticModelSnapshot) -> None:
    issues = [
        issue
        for issue in SemanticModelValidator().validate(snapshot)
        if issue.severity == "error"
    ]
    if issues:
        codes = ", ".join(issue.code for issue in issues)
        raise ValueError(f"semantic model validation failed: {codes}")


def _member_metadata(member: SemanticMember) -> dict[str, object]:
    return {
        "member_id": member.member_id,
        "member_type": member.member_type,
        "aliases": list(member.aliases),
        "ai_context": member.ai_context,
        "source_column_id": member.source_column_id,
    }


def _measure_sql(member: SemanticMember) -> str:
    assert member.measure is not None
    if member.measure.aggregation_type in {"sum", "count", "count_distinct"}:
        return _physical_column_sql(member)
    return _render_expression(member.measure.expression)


def _physical_column_sql(member: SemanticMember) -> str:
    if not member.source_column_id:
        raise ValueError(f"source column is required: {member.qualified_name}")
    return member.source_column_id.rsplit(".", 1)[1]


def _render_expression(expression: str) -> str:
    normalized = _MEMBER_REFERENCE_PATTERN.sub(r"\1", expression)
    parsed = parse_one(normalized, read="mysql")
    return _render_node(parsed)


def _render_node(node: exp.Expression) -> str:
    if isinstance(node, exp.Column):
        table = node.table
        name = node.name
        return (
            f"{{{name}}}"
            if table == "ecommerce"
            else ".".join(part for part in (table, name) if part)
        )
    if isinstance(node, exp.Identifier):
        return node.this
    if isinstance(node, exp.Literal):
        return node.sql(dialect="mysql")
    if isinstance(node, exp.Nullif):
        return f"NULLIF({_render_node(node.this)}, {_render_node(node.expression)})"
    if isinstance(node, exp.Paren):
        return f"({_render_node(node.this)})"
    if isinstance(node, exp.Neg):
        return f"-{_render_node(node.this)}"

    operators: Mapping[type[exp.Expression], str] = {
        exp.Add: " + ",
        exp.Sub: " - ",
        exp.Mul: " * ",
        exp.Div: " / ",
        exp.Mod: " % ",
    }
    for node_type, operator in operators.items():
        if isinstance(node, node_type):
            return f"{_render_node(node.this)}{operator}{_render_node(node.expression)}"
    raise ValueError(f"unsupported validated expression node: {type(node).__name__}")
