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
    SemanticMetricAttachment,
    SemanticMetricEquivalenceGroup,
    SemanticMetricEquivalenceMember,
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


class SemanticMetricEquivalenceMemberPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    member_id: str
    match_type: Literal["exact", "compatible"]
    note: str = ""

    def to_entity(self) -> SemanticMetricEquivalenceMember:
        return SemanticMetricEquivalenceMember(**self.model_dump())


class SemanticMetricEquivalenceGroupPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    canonical_member_id: str
    group_name: str
    description: str
    members: list[SemanticMetricEquivalenceMemberPayload] = Field(default_factory=list)

    def to_entity(self) -> SemanticMetricEquivalenceGroup:
        return SemanticMetricEquivalenceGroup(
            group_id=self.group_id,
            canonical_member_id=self.canonical_member_id,
            group_name=self.group_name,
            description=self.description,
            members=tuple(item.to_entity() for item in self.members),
        )


class SemanticMetricAttachmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_member_id: str
    attached_member_id: str
    relation_type: Literal[
        "supporting",
        "comparison",
        "efficiency",
        "breakdown",
    ]
    display_order: int = 0
    default_visible: bool = False
    note: str = ""

    def to_entity(self) -> SemanticMetricAttachment:
        return SemanticMetricAttachment(**self.model_dump())


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
    calculation_note: str = ""
    unit: str = ""
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
            calculation_note=self.calculation_note,
            unit=self.unit,
            measure=self.measure.to_entity() if self.measure else None,
            dimension=self.dimension.to_entity() if self.dimension else None,
        )


class SemanticDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_version: str
    cubes: list[SemanticCubePayload]
    joins: list[SemanticJoinPayload]
    members: list[SemanticMemberPayload]
    metric_equivalence_groups: list[SemanticMetricEquivalenceGroupPayload] = Field(
        default_factory=list
    )
    metric_attachments: list[SemanticMetricAttachmentPayload] = Field(
        default_factory=list
    )
    reason: str = Field(default="创建语义模型草稿", min_length=1, max_length=500)

    def to_snapshot(self) -> SemanticModelSnapshot:
        return SemanticModelSnapshot(
            release_version=self.release_version,
            cubes=tuple(item.to_entity() for item in self.cubes),
            joins=tuple(item.to_entity() for item in self.joins),
            members=tuple(item.to_entity() for item in self.members),
            metric_equivalence_groups=tuple(
                item.to_entity() for item in self.metric_equivalence_groups
            ),
            metric_attachments=tuple(
                item.to_entity() for item in self.metric_attachments
            ),
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
    calculation_note: str = ""
    unit: str = ""

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
            calculation_note=member.calculation_note,
            unit=member.unit,
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
