"""Cube 受治理成员实体与纯转换逻辑。"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

CubeMemberType = Literal["measure", "dimension", "time_dimension"]


@dataclass(frozen=True)
class CubeMember:
    """可供问数链路检索的 Cube 受治理成员。"""

    name: str
    cube_name: str
    member_type: CubeMemberType
    data_type: str
    title: str
    description: str
    aliases: list[str]
    ai_context: str
    source_column_id: str | None
    filterable: bool


@dataclass(frozen=True)
class CubeMemberEmbeddingEntry:
    """一个 Cube 成员对应的一条确定性向量入口。"""

    id: str
    embedding_kind: str
    embedding_text: str
    member: CubeMember


@dataclass(frozen=True)
class CubeMetadataSyncResult:
    """一次 Cube 元数据同步的摘要。"""

    compiler_id: str | None
    member_count: int
    point_count: int
    collection_name: str


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Cube metadata field {field} must be an object")
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Cube metadata field {field} must be a non-empty string")
    return value


def _validate_source_column_id(source_column_id: str | None) -> None:
    if source_column_id is not None and source_column_id.count(".") != 1:
        raise ValueError("source_column_id must contain exactly one dot")


def _extract_member(
    raw_member: object,
    cube_name: str,
    member_type: CubeMemberType,
) -> CubeMember:
    member = _require_mapping(raw_member, f"{member_type} member")
    name = _require_string(member.get("name"), "member.name")
    data_type = _require_string(member.get("type"), f"{name}.type")
    title = _require_string(member.get("title"), f"{name}.title")
    description = _require_string(member.get("description"), f"{name}.description")

    raw_meta = member.get("meta", {})
    meta = _require_mapping(raw_meta, f"{name}.meta")
    raw_aliases = meta.get("aliases", [])
    if not isinstance(raw_aliases, list) or not all(
        isinstance(alias, str) and alias.strip() for alias in raw_aliases
    ):
        raise ValueError(f"Cube metadata field {name}.meta.aliases must be strings")
    ai_context = meta.get("ai_context", "")
    if not isinstance(ai_context, str):
        raise ValueError(f"Cube metadata field {name}.meta.ai_context must be a string")
    source_column_id = meta.get("source_column_id")
    if source_column_id is not None and not isinstance(source_column_id, str):
        raise ValueError(
            f"Cube metadata field {name}.meta.source_column_id must be a string"
        )
    _validate_source_column_id(source_column_id)
    filterable = meta.get("filterable", False)
    if not isinstance(filterable, bool):
        raise ValueError(f"Cube metadata field {name}.meta.filterable must be boolean")

    return CubeMember(
        name=name,
        cube_name=cube_name,
        member_type=member_type,
        data_type=data_type,
        title=title,
        description=description,
        aliases=list(raw_aliases),
        ai_context=ai_context,
        source_column_id=source_column_id,
        filterable=filterable,
    )


def extract_cube_members(
    metadata: object, semantic_view: str
) -> tuple[list[CubeMember], str | None]:
    """从 Cube ``/v1/meta`` 响应提取指定公开语义视图的成员。"""

    root = _require_mapping(metadata, "root")
    compiler_id = root.get("compilerId")
    if compiler_id is not None and not isinstance(compiler_id, str):
        raise ValueError("Cube metadata field compilerId must be a string or null")
    raw_cubes = root.get("cubes")
    if not isinstance(raw_cubes, list):
        raise ValueError("Cube metadata field cubes must be a list")

    matches: list[Mapping[str, object]] = []
    for index, raw_cube in enumerate(raw_cubes):
        cube = _require_mapping(raw_cube, f"cubes[{index}]")
        if cube.get("name") == semantic_view and cube.get("public") is not False:
            matches.append(cube)
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one public semantic view named {semantic_view!r}"
        )

    cube = matches[0]
    cube_name = _require_string(cube.get("name"), "cube.name")
    raw_measures = cube.get("measures", [])
    raw_dimensions = cube.get("dimensions", [])
    if not isinstance(raw_measures, list) or not isinstance(raw_dimensions, list):
        raise ValueError("Cube measures and dimensions must be lists")

    members: list[CubeMember] = []
    seen_names: set[str] = set()
    for raw_member, default_type in [
        *((measure, "measure") for measure in raw_measures),
        *((dimension, "dimension") for dimension in raw_dimensions),
    ]:
        raw = _require_mapping(raw_member, f"{default_type} member")
        member_type: CubeMemberType = default_type
        if default_type == "dimension" and raw.get("type") == "time":
            member_type = "time_dimension"
        member = _extract_member(raw, cube_name, member_type)
        if member.name in seen_names:
            raise ValueError(f"Cube metadata contains duplicate member {member.name!r}")
        seen_names.add(member.name)
        members.append(member)

    return members, compiler_id


def iter_member_embedding_entries(
    member: CubeMember,
) -> list[CubeMemberEmbeddingEntry]:
    """按固定顺序展开一个成员的语义入口并生成稳定 UUID。"""

    _validate_source_column_id(member.source_column_id)
    parts = [
        ("name", member.name),
        ("title", member.title),
        ("description", member.description),
    ]
    seen_aliases: set[str] = set()
    for alias in member.aliases:
        if alias and alias not in seen_aliases:
            seen_aliases.add(alias)
            parts.append(("alias", alias))
    if member.ai_context:
        parts.append(("ai_context", member.ai_context))

    return [
        CubeMemberEmbeddingEntry(
            id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"cube-member:{member.name}:{embedding_kind}:{embedding_text}",
                )
            ),
            embedding_kind=embedding_kind,
            embedding_text=embedding_text,
            member=member,
        )
        for embedding_kind, embedding_text in parts
    ]
