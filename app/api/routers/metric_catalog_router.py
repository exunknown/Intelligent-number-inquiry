"""Read-only governed metric catalog endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_metric_catalog_service
from app.api.schemas.metric_catalog_schema import (
    CatalogMemberType,
    MetricCatalogItem,
    MetricCatalogResponse,
)
from app.services.metric_catalog_service import MetricCatalogService

metric_catalog_router = APIRouter()


@metric_catalog_router.get(
    "/api/metrics",
    response_model=MetricCatalogResponse,
)
async def metric_catalog_handler(
    member_type: CatalogMemberType = Query("measure"),
    q: str | None = Query(None, max_length=128),
    metric_catalog_service: Annotated[
        MetricCatalogService, Depends(get_metric_catalog_service)
    ] = None,
) -> MetricCatalogResponse:
    """Return the governed Cube catalog used by Text to Metric."""

    members = await metric_catalog_service.list_members(member_type=member_type, q=q)
    items = [MetricCatalogItem.model_validate(member) for member in members]
    return MetricCatalogResponse(items=items, total=len(items))
