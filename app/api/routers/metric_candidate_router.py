"""Read-only metric governance candidate endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import (
    get_metric_candidate_service,
)
from app.api.schemas.metric_candidate_schema import (
    CandidateStatus,
    MetricCandidateItem,
    MetricCandidateResponse,
    MetricCandidateReviewRequest,
)
from app.entities.auth import AuthContext
from app.security.dependencies import require_api_permission
from app.services.metric_candidate_service import MetricCandidateService

metric_candidate_router = APIRouter()
_require_candidate_read = require_api_permission("api:metric-candidates", "read")
_require_candidate_review = require_api_permission("api:metric-candidates", "review")


@metric_candidate_router.get(
    "/api/metric-candidates",
    response_model=MetricCandidateResponse,
)
async def metric_candidate_handler(
    status: CandidateStatus = Query("pending"),
    limit: int = Query(100, ge=1, le=200),
    metric_candidate_service: Annotated[
        MetricCandidateService, Depends(get_metric_candidate_service)
    ] = None,
    _auth: Annotated[AuthContext, Depends(_require_candidate_read)] = None,
) -> MetricCandidateResponse:
    """Return recent questions that need metric governance."""

    candidates = await metric_candidate_service.list_candidates(
        status=status, limit=limit
    )
    items = [MetricCandidateItem.model_validate(candidate) for candidate in candidates]
    return MetricCandidateResponse(items=items, total=len(items))


@metric_candidate_router.post(
    "/api/metric-candidates/{candidate_id}/review",
    response_model=MetricCandidateItem,
)
async def metric_candidate_review_handler(
    candidate_id: str,
    request: MetricCandidateReviewRequest,
    metric_candidate_service: Annotated[
        MetricCandidateService, Depends(get_metric_candidate_service)
    ] = None,
    _auth: Annotated[AuthContext, Depends(_require_candidate_review)] = None,
) -> MetricCandidateItem:
    """Approve or reject one governance candidate."""

    candidate = await metric_candidate_service.review_candidate(
        candidate_id=candidate_id,
        status=request.status,
        review_note=request.review_note,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="metric candidate not found")
    return MetricCandidateItem.model_validate(candidate)
