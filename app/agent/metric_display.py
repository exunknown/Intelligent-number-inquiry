"""Build the safe metric display projection used by SSE and session snapshots."""

from collections.abc import Mapping
from typing import Literal

from app.entities.cube_member import CubeMember

MetricDisplayRole = Literal["primary", "attached"]


def metric_display_entry(
    member: CubeMember,
    role: MetricDisplayRole,
    source_member_id: str | None = None,
    compatibility_note: str | None = None,
) -> dict[str, str | None]:
    """Project a Cube member to the fields allowed in a client-facing event."""

    entry = {
        "member_id": member.name,
        "title": member.title or member.name,
        "role": role,
        "source_member_id": source_member_id,
    }
    if compatibility_note:
        entry["compatibility_note"] = compatibility_note
    return entry


def governed_metric_display_entries(
    state: Mapping[str, object],
) -> list[dict[str, str | None]]:
    """Project only the permission-filtered, relation-normalized metric state."""

    primary_metrics = state.get("resolved_primary_metrics")
    if not isinstance(primary_metrics, list):
        primary = state.get("resolved_primary_metric")
        primary_metrics = [primary] if isinstance(primary, CubeMember) else []
    attached = state.get("resolved_attached_metrics", [])
    if not isinstance(attached, list):
        attached = []
    attached_sources = state.get("resolved_attached_metric_sources", {})
    if not isinstance(attached_sources, dict):
        attached_sources = {}
    compatibility_notes = state.get("resolved_compatibility_notes", {})
    if not isinstance(compatibility_notes, dict):
        compatibility_notes = {}

    entries: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for primary in primary_metrics:
        if not isinstance(primary, CubeMember) or primary.name in seen:
            continue
        note = compatibility_notes.get(primary.name)
        entries.append(
            metric_display_entry(
                primary,
                "primary",
                compatibility_note=note if isinstance(note, str) else None,
            )
        )
        seen.add(primary.name)
    for member in attached:
        if not isinstance(member, CubeMember) or member.name in seen:
            continue
        source_member_id = attached_sources.get(member.name)
        entries.append(
            metric_display_entry(
                member,
                "attached",
                source_member_id=(
                    source_member_id if isinstance(source_member_id, str) else None
                ),
            )
        )
        seen.add(member.name)
    return entries


def legacy_metric_display_entries(
    state: Mapping[str, object],
) -> list[dict[str, str | None]]:
    """Project recalled measures for pre-governance selector/SQL display only."""

    entries: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for member in state.get("retrieved_cube_measures", []):
        if not isinstance(member, CubeMember) or member.name in seen:
            continue
        entries.append(metric_display_entry(member, "primary"))
        seen.add(member.name)
    return entries
