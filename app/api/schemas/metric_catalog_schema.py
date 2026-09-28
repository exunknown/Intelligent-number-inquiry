"""Metric catalog API response models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

CatalogMemberType = Literal["measure", "dimension", "time_dimension", "all"]


class MetricCatalogItem(BaseModel):
    """A governed Cube member exposed to catalog consumers."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    cube_name: str
    member_type: Literal["measure", "dimension", "time_dimension"]
    data_type: str
    title: str
    description: str
    aliases: list[str]
    ai_context: str
    source_column_id: str | None
    filterable: bool


class MetricCatalogResponse(BaseModel):
    """A filtered snapshot of the governed Cube member catalog."""

    items: list[MetricCatalogItem]
    total: int
