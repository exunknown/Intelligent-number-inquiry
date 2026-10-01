"""Read-only service for the governed Cube member catalog."""

from typing import Literal

from app.entities.auth import PermissionSnapshot
from app.entities.cube_member import CubeMember
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)

CatalogMemberFilter = Literal["measure", "dimension", "time_dimension", "all"]


class MetricCatalogService:
    """Load the current Qdrant alias snapshot and apply API filters."""

    def __init__(
        self,
        repository: CubeMemberQdrantRepository,
        semantic_repository=None,
    ):
        self.repository = repository
        self.semantic_repository = semantic_repository

    async def list_members(
        self,
        member_type: CatalogMemberFilter = "measure",
        q: str | None = None,
        permissions: PermissionSnapshot | None = None,
    ) -> list[CubeMember]:
        """Return governed members matching type and human-readable search text."""

        if self.semantic_repository is None:
            members = await self.repository.list_members()
        else:
            snapshot = await self.semantic_repository.get_active_snapshot()
            members = (
                []
                if snapshot is None
                else [
                    CubeMember(
                        name=member.qualified_name,
                        cube_name=member.cube_name,
                        member_type=member.member_type,
                        data_type=member.data_type,
                        title=member.title,
                        description=member.description,
                        aliases=list(member.aliases),
                        ai_context=member.ai_context,
                        source_column_id=member.source_column_id,
                        filterable=member.filterable,
                    )
                    for member in snapshot.members
                ]
            )
        normalized_query = q.strip().casefold() if q else ""
        result = []
        for member in members:
            if member_type != "all" and member.member_type != member_type:
                continue
            if normalized_query:
                searchable = " ".join(
                    [
                        member.name,
                        member.title,
                        member.description,
                        *member.aliases,
                    ]
                ).casefold()
                if normalized_query not in searchable:
                    continue
            if permissions is not None and not self._is_allowed(member, permissions):
                continue
            result.append(member)
        return result

    @staticmethod
    def _is_allowed(member: CubeMember, permissions: PermissionSnapshot) -> bool:
        if member.member_type == "measure":
            return member.name in permissions.allowed_metrics
        return (
            member.source_column_id is not None
            and member.source_column_id in permissions.allowed_columns
        )
