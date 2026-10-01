"""指标维度治理 API 的请求和响应模型。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.entities.semantic_model import (
    SemanticCube,
    SemanticDimensionDefinition,
    SemanticJoin,
    SemanticMeasureDefinition,
    SemanticMember,
    SemanticModelSnapshot,
)


class SemanticCubePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_version: str
    cube_name: str
    sql_table: str
    title: str
    description: str
    public: bool = False

    def to_entity(self) -> SemanticCube:
        return SemanticCube(**self.model_dump())


class SemanticJoinPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_version: str
    cube_name: str
    target_cube_name: str
    sql_expression: str
    relationship: str
    editable: bool = False

    def to_entity(self) -> SemanticJoin:
        return SemanticJoin(**self.model_dump())


class SemanticMeasurePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str
    aggregation_type: Literal["sum", "count", "count_distinct", "number"]
    dependency_members: list[str] = Field(default_factory=list)

    def to_entity(self) -> SemanticMeasureDefinition:
        return SemanticMeasureDefinition(
            expression=self.expression,
            aggregation_type=self.aggregation_type,
            dependency_members=tuple(self.dependency_members),
        )


class SemanticDimensionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension_type: Literal["string", "number", "time"]
    time_granularity: str | None = None
    primary_key: bool = False

    def to_entity(self) -> SemanticDimensionDefinition:
        return SemanticDimensionDefinition(
            dimension_type=self.dimension_type,
            time_granularity=self.time_granularity,
            primary_key=self.primary_key,
        )


class SemanticMemberPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_version: str
    member_id: str
    cube_name: str
    member_name: str
    member_type: Literal["measure", "dimension", "time_dimension"]
    title: str
    description: str
    data_type: str
    source_column_id: str | None = None
    ai_context: str = ""
    aliases: list[str] = Field(default_factory=list)
    filterable: bool = False
    groupable: bool = False
    status: str = "published"
    measure: SemanticMeasurePayload | None = None
    dimension: SemanticDimensionPayload | None = None

    def to_entity(self) -> SemanticMember:
        return SemanticMember(
            release_version=self.release_version,
            member_id=self.member_id,
            cube_name=self.cube_name,
            member_name=self.member_name,
            member_type=self.member_type,
            title=self.title,
            description=self.description,
            data_type=self.data_type,
            source_column_id=self.source_column_id,
            ai_context=self.ai_context,
            aliases=tuple(self.aliases),
            filterable=self.filterable,
            groupable=self.groupable,
            status=self.status,
            measure=self.measure.to_entity() if self.measure else None,
            dimension=self.dimension.to_entity() if self.dimension else None,
        )


class SemanticDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_version: str
    cubes: list[SemanticCubePayload]
    joins: list[SemanticJoinPayload]
    members: list[SemanticMemberPayload]
    reason: str = Field(default="创建语义模型草稿", min_length=1, max_length=500)

    def to_snapshot(self) -> SemanticModelSnapshot:
        return SemanticModelSnapshot(
            release_version=self.release_version,
            cubes=tuple(item.to_entity() for item in self.cubes),
            joins=tuple(item.to_entity() for item in self.joins),
            members=tuple(item.to_entity() for item in self.members),
        )


class SemanticMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    member_id: str
    cube_name: str
    member_name: str
    member_type: Literal["measure", "dimension", "time_dimension"]
    title: str
    description: str
    data_type: str
    source_column_id: str | None
    aliases: list[str]
    filterable: bool
    groupable: bool

    @classmethod
    def from_entity(cls, member: SemanticMember) -> "SemanticMemberResponse":
        return cls(
            member_id=member.member_id,
            cube_name=member.cube_name,
            member_name=member.member_name,
            member_type=member.member_type,
            title=member.title,
            description=member.description,
            data_type=member.data_type,
            source_column_id=member.source_column_id,
            aliases=list(member.aliases),
            filterable=member.filterable,
            groupable=member.groupable,
        )


class SemanticMemberListResponse(BaseModel):
    items: list[SemanticMemberResponse]
    total: int


class SemanticValidationIssueResponse(BaseModel):
    code: str
    path: str
    message: str
    severity: Literal["error", "warning"]


class SemanticOperationResponse(BaseModel):
    operation_id: str
    status: str
    draft_id: str | None = None
    release_version: str | None = None
    error_code: str | None = None
    issues: list[SemanticValidationIssueResponse] = Field(default_factory=list)


class SemanticDraftResponse(BaseModel):
    draft_id: str
    release_version: str
    status: str
    snapshot: SemanticDraftRequest
    review_note: str | None = None
    updated_at: datetime | None = None


class SemanticReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


class SemanticActionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SemanticReleaseResponse(BaseModel):
    release_version: str
    status: str
    active: bool = False
    error_code: str | None = None
    snapshot: SemanticDraftRequest | None = None


class SemanticReleaseListResponse(BaseModel):
    items: list[SemanticReleaseResponse]
    total: int


class SemanticRollbackRequest(SemanticActionRequest):
    idempotency_key: UUID | None = None
