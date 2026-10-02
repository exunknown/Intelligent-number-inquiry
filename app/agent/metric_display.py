"""Build the safe metric display projection used by SSE and session snapshots."""

from collections.abc import Mapping
from typing import Literal

from app.entities.cube_member import CubeMember

MetricDisplayRole = Literal["primary", "attached"]


def metric_display_entry(
    member: CubeMember,
    role: MetricDisplayRole,
    source_member_id: str | None = None,
) -> dict[str, str | None]:
    """Project a Cube member to the fields allowed in a client-facing event."""

    return {
        "member_id": member.name,
        "title": member.title or member.name,
        "role": role,
        "source_member_id": source_member_id,
    }


def metric_display_entries(state: Mapping[str, object]) -> list[dict[str, str | None]]:
    """Return unique primary/attached metric entries from governed state."""

    primary = state.get("resolved_primary_metric")
    attached = state.get("resolved_attached_metrics", [])
    if not isinstance(attached, list):
        attached = []

    entries: list[dict[str, str | None]] = []
    seen: set[str] = set()
    if isinstance(primary, CubeMember):
        entries.append(metric_display_entry(primary, "primary"))
        seen.add(primary.name)
        for member in attached:
            if not isinstance(member, CubeMember) or member.name in seen:
                continue
            entries.append(
                metric_display_entry(member, "attached", source_member_id=primary.name)
            )
            seen.add(member.name)
        return entries

    for member in state.get("retrieved_cube_measures", []):
        if not isinstance(member, CubeMember) or member.name in seen:
            continue
        entries.append(metric_display_entry(member, "primary"))
        seen.add(member.name)
    return entries
