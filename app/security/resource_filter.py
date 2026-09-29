"""模型上下文使用的精确资源权限过滤。"""

from typing import TypeVar

from app.entities.auth import PermissionSnapshot

T = TypeVar("T")


def filter_columns(columns: list[T], snapshot: PermissionSnapshot) -> list[T]:
    return [
        column
        for column in columns
        if getattr(column, "id", None) in snapshot.allowed_columns
    ]


def filter_values(values: list[T], snapshot: PermissionSnapshot) -> list[T]:
    return [
        value
        for value in values
        if getattr(value, "column_id", None) in snapshot.allowed_columns
    ]


def filter_cube_members(members: list[T], snapshot: PermissionSnapshot) -> list[T]:
    result = []
    for member in members:
        if getattr(member, "member_type", None) == "measure":
            if getattr(member, "name", None) in snapshot.allowed_metrics:
                result.append(member)
        elif getattr(member, "source_column_id", None) in snapshot.allowed_columns:
            result.append(member)
    return result


def filter_tables(tables: list[T], snapshot: PermissionSnapshot) -> list[T]:
    return [
        table
        for table in tables
        if (getattr(table, "id", None) or getattr(table, "name", None))
        in snapshot.allowed_tables
    ]
