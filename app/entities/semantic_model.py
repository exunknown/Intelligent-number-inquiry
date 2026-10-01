"""指标、维度和 Cube 运行模型的语义层实体。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeAlias

MemberType: TypeAlias = Literal["measure", "dimension", "time_dimension"]
AggregationType: TypeAlias = Literal["sum", "count", "count_distinct", "number"]
DimensionType: TypeAlias = Literal["string", "number", "time"]


@dataclass(frozen=True)
class SemanticCube:
    """一个发布版本中的 Cube 定义。"""

    release_version: str
    cube_name: str
    sql_table: str
    title: str
    description: str
    public: bool

    def to_dict(self) -> dict:
        return {
            "release_version": self.release_version,
            "cube_name": self.cube_name,
            "sql_table": self.sql_table,
            "title": self.title,
            "description": self.description,
            "public": self.public,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SemanticCube":
        return cls(**value)


@dataclass(frozen=True)
class SemanticJoin:
    """一个发布版本中的 Cube Join 定义。"""

    release_version: str
    cube_name: str
    target_cube_name: str
    sql_expression: str
    relationship: str
    editable: bool

    def to_dict(self) -> dict:
        return {
            "release_version": self.release_version,
            "cube_name": self.cube_name,
            "target_cube_name": self.target_cube_name,
            "sql_expression": self.sql_expression,
            "relationship": self.relationship,
            "editable": self.editable,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SemanticJoin":
        return cls(**value)


@dataclass(frozen=True)
class SemanticMeasureDefinition:
    """指标特有的计算定义。"""

    expression: str
    aggregation_type: AggregationType
    dependency_members: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "aggregation_type": self.aggregation_type,
            "dependency_members": list(self.dependency_members),
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SemanticMeasureDefinition":
        return cls(
            expression=value["expression"],
            aggregation_type=value["aggregation_type"],
            dependency_members=tuple(value.get("dependency_members", ())),
        )


@dataclass(frozen=True)
class SemanticDimensionDefinition:
    """维度特有的分组、时间和主键定义。"""

    dimension_type: DimensionType
    time_granularity: str | None
    primary_key: bool

    def to_dict(self) -> dict:
        return {
            "dimension_type": self.dimension_type,
            "time_granularity": self.time_granularity,
            "primary_key": self.primary_key,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SemanticDimensionDefinition":
        return cls(
            dimension_type=value["dimension_type"],
            time_granularity=value.get("time_granularity"),
            primary_key=value.get("primary_key", False),
        )


@dataclass(frozen=True)
class SemanticMember:
    """Cube 对外暴露的指标、维度或时间维度。"""

    release_version: str
    member_id: str
    cube_name: str
    member_name: str
    member_type: MemberType
    title: str
    description: str
    data_type: str
    source_column_id: str | None
    ai_context: str
    aliases: tuple[str, ...]
    filterable: bool
    groupable: bool
    status: str = "published"
    measure: SemanticMeasureDefinition | None = None
    dimension: SemanticDimensionDefinition | None = None

    def __post_init__(self) -> None:
        if self.member_type == "measure" and self.measure is None:
            raise ValueError("measure member requires measure definition")
        if self.member_type != "measure" and self.dimension is None:
            raise ValueError("dimension member requires dimension definition")
        if self.member_type == "measure" and self.dimension is not None:
            raise ValueError("measure member cannot have dimension definition")
        if self.member_type != "measure" and self.measure is not None:
            raise ValueError("dimension member cannot have measure definition")

    @property
    def qualified_name(self) -> str:
        return f"{self.cube_name}.{self.member_name}"

    def to_dict(self) -> dict:
        return {
            "release_version": self.release_version,
            "member_id": self.member_id,
            "cube_name": self.cube_name,
            "member_name": self.member_name,
            "member_type": self.member_type,
            "title": self.title,
            "description": self.description,
            "data_type": self.data_type,
            "source_column_id": self.source_column_id,
            "ai_context": self.ai_context,
            "aliases": list(self.aliases),
            "filterable": self.filterable,
            "groupable": self.groupable,
            "status": self.status,
            "measure": self.measure.to_dict() if self.measure else None,
            "dimension": self.dimension.to_dict() if self.dimension else None,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SemanticMember":
        return cls(
            release_version=value["release_version"],
            member_id=value["member_id"],
            cube_name=value["cube_name"],
            member_name=value["member_name"],
            member_type=value["member_type"],
            title=value["title"],
            description=value["description"],
            data_type=value["data_type"],
            source_column_id=value.get("source_column_id"),
            ai_context=value.get("ai_context", ""),
            aliases=tuple(value.get("aliases", ())),
            filterable=value.get("filterable", False),
            groupable=value.get("groupable", False),
            status=value.get("status", "published"),
            measure=(
                SemanticMeasureDefinition.from_dict(value["measure"])
                if value.get("measure") is not None
                else None
            ),
            dimension=(
                SemanticDimensionDefinition.from_dict(value["dimension"])
                if value.get("dimension") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class SemanticModelSnapshot:
    """一个可校验、可发布的完整语义模型快照。"""

    release_version: str
    cubes: tuple[SemanticCube, ...]
    joins: tuple[SemanticJoin, ...]
    members: tuple[SemanticMember, ...]
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "release_version": self.release_version,
            "cubes": [cube.to_dict() for cube in self.cubes],
            "joins": [join.to_dict() for join in self.joins],
            "members": [member.to_dict() for member in self.members],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "SemanticModelSnapshot":
        created_at = value.get("created_at")
        return cls(
            release_version=value["release_version"],
            cubes=tuple(
                SemanticCube.from_dict(item) for item in value.get("cubes", ())
            ),
            joins=tuple(
                SemanticJoin.from_dict(item) for item in value.get("joins", ())
            ),
            members=tuple(
                SemanticMember.from_dict(item) for item in value.get("members", ())
            ),
            created_at=datetime.fromisoformat(created_at) if created_at else None,
        )
