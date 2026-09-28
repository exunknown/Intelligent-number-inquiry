"""Read-only service for the governed Cube member catalog."""

from typing import Literal

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
            result.append(member)
        return result
