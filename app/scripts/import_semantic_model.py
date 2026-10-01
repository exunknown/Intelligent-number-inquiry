"""将现有 Cube YAML 导入语义模型草稿。"""

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from app.entities.semantic_model import (
    SemanticCube,
    SemanticDimensionDefinition,
    SemanticJoin,
    SemanticMeasureDefinition,
    SemanticMember,
    SemanticModelSnapshot,
)

_MEMBER_REFERENCE_PATTERN = re.compile(r"\{([^{}]+)\}")


def import_yaml_model(source: Path, release_version: str) -> SemanticModelSnapshot:
    """读取 Cube YAML 目录并生成可校验的语义模型快照。"""

    documents = _load_documents(source)
    view = documents.get("ecommerce")
    if not isinstance(view, dict):
        raise ValueError("ecommerce.yml must define a mapping")

    cube_definitions = _cube_definitions(documents)
    cubes = [_view_cube(view, release_version)]
    cubes.extend(
        _cube_entity(cube, release_version)
        for cube in sorted(cube_definitions.values(), key=lambda item: item["name"])
    )
    joins = tuple(
        join
        for cube in sorted(cube_definitions.values(), key=lambda item: item["name"])
        for join in _join_entities(cube, release_version)
    )
    members = _public_members(view, cube_definitions, release_version)
    return SemanticModelSnapshot(
        release_version=release_version,
        cubes=tuple(cubes),
        joins=joins,
        members=members,
    )


def snapshot_hash(snapshot: SemanticModelSnapshot) -> str:
    """生成不受字段顺序影响的快照 hash，用于幂等导入判断。"""

    payload = json.dumps(
        snapshot.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def persist_snapshot_draft(
    snapshot: SemanticModelSnapshot,
    actor_id: str,
) -> tuple[str, bool]:
    """将快照写入 Meta MySQL；相同快照的现有草稿会被复用。"""

    from sqlalchemy import select

    from app.clients.mysql_client_manager import meta_mysql_client_manager
    from app.models.semantic_draft import SemanticModelDraftMySQL
    from app.repositories.mysql.meta.semantic_model_repository import (
        SemanticModelRepository,
    )

    meta_mysql_client_manager.init()
    try:
        async with meta_mysql_client_manager.session_factory() as session:
            result = await session.execute(
                select(SemanticModelDraftMySQL).where(
                    SemanticModelDraftMySQL.release_version == snapshot.release_version,
                    SemanticModelDraftMySQL.status.in_(["draft", "rejected"]),
                )
            )
            target_hash = snapshot_hash(snapshot)
            for model in result.scalars().all():
                existing = SemanticModelSnapshot.from_dict(model.snapshot_json)
                if snapshot_hash(existing) == target_hash:
                    return model.draft_id, False
            draft_id = await SemanticModelRepository(session).create_draft(
                snapshot,
                created_by=actor_id,
            )
            return draft_id, True
    finally:
        await meta_mysql_client_manager.close()


def _load_documents(source: Path) -> dict[str, dict[str, Any]]:
    root = source if source.is_dir() else source.parent
    paths = [source] if source.is_file() else sorted(root.glob("*.yml"))
    if not paths:
        raise ValueError(f"no YAML files found under {root}")
    documents: dict[str, dict[str, Any]] = {}
    for path in paths:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(content, dict):
            raise ValueError(f"YAML document must be a mapping: {path.name}")
        documents[path.stem] = content
    return documents


def _cube_definitions(
    documents: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    cubes: dict[str, dict[str, Any]] = {}
    for document in documents.values():
        for cube in document.get("cubes", []):
            if not isinstance(cube, dict) or not isinstance(cube.get("name"), str):
                raise ValueError("every cube must define a name")
            name = cube["name"]
            if name in cubes:
                raise ValueError(f"duplicate cube definition: {name}")
            cubes[name] = cube
    return cubes


def _view_cube(view: dict[str, Any], release_version: str) -> SemanticCube:
    name = view.get("views", [{}])[0].get("name", "ecommerce")
    view_definition = next(
        (item for item in view.get("views", []) if item.get("name") == name),
        None,
    )
    if not isinstance(view_definition, dict):
        raise ValueError("ecommerce.yml must define a named view")
    return SemanticCube(
        release_version=release_version,
        cube_name=name,
        sql_table="",
        title=str(view_definition.get("title", name)),
        description=str(view_definition.get("description", "")),
        public=bool(view_definition.get("public", True)),
    )


def _cube_entity(cube: dict[str, Any], release_version: str) -> SemanticCube:
    name = str(cube["name"])
    return SemanticCube(
        release_version=release_version,
        cube_name=name,
        sql_table=str(cube.get("sql_table", "")),
        title=str(cube.get("title", name)),
        description=str(cube.get("description", "")),
        public=bool(cube.get("public", False)),
    )


def _join_entities(
    cube: dict[str, Any], release_version: str
) -> tuple[SemanticJoin, ...]:
    source_name = str(cube["name"])
    return tuple(
        SemanticJoin(
            release_version=release_version,
            cube_name=source_name,
            target_cube_name=str(join["name"]),
            sql_expression=str(join["sql"]),
            relationship=str(join["relationship"]),
            editable=False,
        )
        for join in sorted(cube.get("joins", []), key=lambda item: str(item["name"]))
    )


def _public_members(
    view: dict[str, Any],
    cubes: dict[str, dict[str, Any]],
    release_version: str,
) -> tuple[SemanticMember, ...]:
    views = view.get("views", [])
    view_definition = next(
        (item for item in views if item.get("name") == "ecommerce"), None
    )
    if not isinstance(view_definition, dict):
        raise ValueError("ecommerce view is missing")
    result: list[SemanticMember] = []
    seen: set[tuple[str, str]] = set()
    for exposure in view_definition.get("cubes", []):
        join_path = str(exposure.get("join_path", ""))
        source_name = join_path.rsplit(".", 1)[-1]
        source_cube_name = join_path.split(".", 1)[0]
        cube = cubes.get(source_name)
        if cube is None or source_cube_name not in cubes:
            raise ValueError(f"view join path references an unknown cube: {join_path}")
        for member_name in exposure.get("includes", []):
            key = ("ecommerce", str(member_name))
            if key in seen:
                raise ValueError(f"duplicate public member: ecommerce.{member_name}")
            seen.add(key)
            definition = _find_member_definition(cube, str(member_name))
            result.append(_member_entity(definition, release_version))
    return tuple(result)


def _find_member_definition(cube: dict[str, Any], member_name: str) -> dict[str, Any]:
    for member_type in ("measures", "dimensions"):
        for member in cube.get(member_type, []):
            if member.get("name") == member_name:
                return {
                    **member,
                    "member_type": "measure"
                    if member_type == "measures"
                    else "dimension",
                    "cube_name": "ecommerce",
                }
    raise ValueError(
        f"public member is not defined in cube {cube['name']}: {member_name}"
    )


def _member_entity(definition: dict[str, Any], release_version: str) -> SemanticMember:
    member_type = str(definition["member_type"])
    member_name = str(definition["name"])
    meta = definition.get("meta") or {}
    source_column_id = meta.get("source_column_id")
    title = str(definition.get("title", member_name))
    description = str(definition.get("description", ""))
    aliases = _normalize_aliases(meta.get("aliases", []))
    if member_type == "measure":
        aggregation_type = str(definition.get("type", "number"))
        expression = str(source_column_id or definition.get("sql", ""))
        if aggregation_type == "number":
            expression = str(definition.get("sql", expression))
        return SemanticMember(
            release_version=release_version,
            member_id=f"measure:ecommerce:{member_name}",
            cube_name="ecommerce",
            member_name=member_name,
            member_type="measure",
            title=title,
            description=description,
            data_type="number",
            source_column_id=str(source_column_id) if source_column_id else None,
            ai_context=str(meta.get("ai_context", "")),
            aliases=aliases,
            filterable=bool(meta.get("filterable", False)),
            groupable=False,
            measure=SemanticMeasureDefinition(
                expression=expression,
                aggregation_type=aggregation_type,
                dependency_members=_dependencies(expression),
            ),
        )

    dimension_type = str(definition.get("type", "string"))
    is_time = dimension_type == "time"
    return SemanticMember(
        release_version=release_version,
        member_id=f"{'time_dimension' if is_time else 'dimension'}:ecommerce:{member_name}",
        cube_name="ecommerce",
        member_name=member_name,
        member_type="time_dimension" if is_time else "dimension",
        title=title,
        description=description,
        data_type="date" if is_time else dimension_type,
        source_column_id=str(source_column_id) if source_column_id else None,
        ai_context=str(meta.get("ai_context", "")),
        aliases=aliases,
        filterable=bool(meta.get("filterable", False)),
        groupable=True,
        dimension=SemanticDimensionDefinition(
            dimension_type=dimension_type,
            time_granularity=str(meta.get("time_granularity", "day"))
            if is_time
            else None,
            primary_key=bool(definition.get("primary_key", False)),
        ),
    )


def _dependencies(expression: str) -> tuple[str, ...]:
    result: list[str] = []
    for value in _MEMBER_REFERENCE_PATTERN.findall(expression):
        qualified = value if "." in value else f"ecommerce.{value}"
        if qualified not in result:
            result.append(qualified)
    return tuple(result)


def _normalize_aliases(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    result: list[str] = []
    for value in values:
        alias = str(value).strip()
        if alias and alias not in result:
            result.append(alias)
    return tuple(result)


def _main() -> None:
    parser = argparse.ArgumentParser(description="将 Cube YAML 导入语义模型草稿")
    parser.add_argument("--source", type=Path, default=Path("cube/model"))
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--persist", action="store_true", help="写入 Meta MySQL 草稿")
    parser.add_argument("--actor-id", help="--persist 时必填的操作者 ID")
    args = parser.parse_args()
    snapshot = import_yaml_model(args.source, args.release_version)
    if args.persist:
        if not args.actor_id:
            parser.error("--persist requires --actor-id")
        draft_id, created = asyncio.run(
            persist_snapshot_draft(snapshot, actor_id=args.actor_id)
        )
        print(
            json.dumps({"draft_id": draft_id, "created": created}, ensure_ascii=False)
        )
        return
    print(
        json.dumps(
            {
                "release_version": snapshot.release_version,
                "snapshot_sha256": snapshot_hash(snapshot),
                "cube_count": len(snapshot.cubes),
                "join_count": len(snapshot.joins),
                "member_count": len(snapshot.members),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    _main()
