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

    def __init__(self, repository: CubeMemberQdrantRepository):
        self.repository = repository

    async def list_members(
        self,
        member_type: CatalogMemberFilter = "measure",
        q: str | None = None,
        permissions: PermissionSnapshot | None = None,
    ) -> list[CubeMember]:
        """Return governed members matching type and human-readable search text."""

        members = await self.repository.list_members()
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
