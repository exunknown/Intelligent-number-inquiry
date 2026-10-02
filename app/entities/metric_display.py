"""Client-facing metric display item projections."""

from collections.abc import Mapping
from typing import Literal, TypedDict


class MetricDisplayEntry(TypedDict, total=False):
    """The only structured metric fields allowed outside the agent graph."""

    member_id: str
    title: str
    role: Literal["primary", "attached"]
    source_member_id: str | None
    compatibility_note: str


MetricDisplayItem = str | MetricDisplayEntry


def safe_metric_display_item(value: object) -> MetricDisplayItem | None:
    """Project legacy strings and structured entries to the public allowlist."""

    if isinstance(value, str):
        return value
    if not isinstance(value, Mapping):
        return None

    member_id = value.get("member_id")
    title = value.get("title")
    if not isinstance(member_id, str) or not member_id:
        return None
    if not isinstance(title, str) or not title:
        return None

    entry: MetricDisplayEntry = {"member_id": member_id, "title": title}
    role = value.get("role")
    if role in {"primary", "attached"}:
        entry["role"] = role
    source_member_id = value.get("source_member_id")
    if source_member_id is None or isinstance(source_member_id, str):
        entry["source_member_id"] = source_member_id
    compatibility_note = value.get("compatibility_note")
    if isinstance(compatibility_note, str) and compatibility_note:
        entry["compatibility_note"] = compatibility_note
    return entry


def safe_metric_display_items(value: object) -> list[MetricDisplayItem]:
    """Project a stored/event metrics array without carrying unknown keys."""

    if not isinstance(value, list):
        return []
    return [
        item
        for raw_item in value
        if (item := safe_metric_display_item(raw_item)) is not None
    ]
