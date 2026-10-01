"""指标维度语义模型治理接口。"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.dependencies import get_semantic_model_service
from app.api.schemas.semantic_model_schema import (
    SemanticActionRequest,
    SemanticDraftRequest,
    SemanticDraftResponse,
    SemanticMemberListResponse,
    SemanticMemberResponse,
    SemanticOperationResponse,
    SemanticReleaseListResponse,
    SemanticReleaseResponse,
    SemanticReviewRequest,
)
from app.entities.auth import AuthContext
from app.security.dependencies import require_api_permission
from app.services.semantic_model_service import (
    SemanticModelService,
    SemanticOperationResult,
)

semantic_model_router = APIRouter()
_require_read = require_api_permission("api:semantic-model", "read")
_require_edit = require_api_permission("api:semantic-model", "edit")
_require_review = require_api_permission("api:semantic-model", "review")
_require_publish = require_api_permission("api:semantic-model", "publish")
_require_rollback = require_api_permission("api:semantic-model", "rollback")

MemberTypeQuery = Literal["measure", "dimension", "time_dimension", "all"]


@semantic_model_router.get(
    "/api/admin/semantic-model/members",
    response_model=SemanticMemberListResponse,
)
async def list_semantic_members_handler(
    member_type: MemberTypeQuery = Query("all"),
    q: str | None = Query(None, max_length=128),
    service: Annotated[
        SemanticModelService, Depends(get_semantic_model_service)
    ] = None,
    _auth: Annotated[AuthContext, Depends(_require_read)] = None,
) -> SemanticMemberListResponse:
    members = await service.list_members(member_type=member_type, q=q)
    items = [SemanticMemberResponse.from_entity(member) for member in members]
    return SemanticMemberListResponse(items=items, total=len(items))


@semantic_model_router.get(
    "/api/admin/semantic-model/members/{member_id}",
    response_model=SemanticMemberResponse,
)
async def get_semantic_member_handler(
    member_id: str,
    service: Annotated[
        SemanticModelService, Depends(get_semantic_model_service)
    ] = None,
    _auth: Annotated[AuthContext, Depends(_require_read)] = None,
) -> SemanticMemberResponse:
    members = await service.list_members(member_type="all")
    member = next((item for item in members if item.member_id == member_id), None)
    if member is None:
        raise HTTPException(status_code=404, detail="semantic member not found")
    return SemanticMemberResponse.from_entity(member)


@semantic_model_router.post(
    "/api/admin/semantic-model/drafts",
    response_model=SemanticOperationResponse,
    status_code=201,
)
async def create_semantic_draft_handler(
    request: SemanticDraftRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_edit)],
    service: Annotated[SemanticModelService, Depends(get_semantic_model_service)],
) -> SemanticOperationResponse:
    try:
        result = await service.create_draft(
            request.to_snapshot(),
            auth.user_id,
            request.reason,
            str(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _operation_response(result)


@semantic_model_router.get(
    "/api/admin/semantic-model/drafts/{draft_id}",
    response_model=SemanticDraftResponse,
)
async def get_semantic_draft_handler(
    draft_id: str,
    service: Annotated[
        SemanticModelService, Depends(get_semantic_model_service)
    ] = None,
    _auth: Annotated[AuthContext, Depends(_require_read)] = None,
) -> SemanticDraftResponse:
    record = await service.get_draft(draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="semantic model draft not found")
    snapshot = record["snapshot"]
    return SemanticDraftResponse(
        draft_id=record["draft_id"],
        release_version=snapshot.release_version,
        status=record["status"],
        snapshot=SemanticDraftRequest.model_validate(
            {
                **{
                    key: value
                    for key, value in snapshot.to_dict().items()
                    if key != "created_at"
                },
                "reason": "读取语义模型草稿",
            }
        ),
        review_note=record.get("review_note"),
        updated_at=record.get("updated_at"),
    )


@semantic_model_router.put(
    "/api/admin/semantic-model/drafts/{draft_id}",
    response_model=SemanticOperationResponse,
)
async def update_semantic_draft_handler(
    draft_id: str,
    request: SemanticDraftRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_edit)],
    service: Annotated[SemanticModelService, Depends(get_semantic_model_service)],
) -> SemanticOperationResponse:
    try:
        result = await service.update_draft(
            draft_id,
            request.to_snapshot(),
            auth.user_id,
            request.reason,
            str(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _operation_response(result)


@semantic_model_router.post(
    "/api/admin/semantic-model/drafts/{draft_id}/validate",
    response_model=SemanticOperationResponse,
)
async def validate_semantic_draft_handler(
    draft_id: str,
    auth: Annotated[AuthContext, Depends(_require_edit)],
    service: Annotated[SemanticModelService, Depends(get_semantic_model_service)],
) -> SemanticOperationResponse:
    del auth
    try:
        result = await service.validate_draft(draft_id, actor_id="")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _operation_response(result)


@semantic_model_router.post(
    "/api/admin/semantic-model/drafts/{draft_id}/submit",
    response_model=SemanticOperationResponse,
)
async def submit_semantic_draft_handler(
    draft_id: str,
    request: SemanticActionRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_edit)],
    service: Annotated[SemanticModelService, Depends(get_semantic_model_service)],
) -> SemanticOperationResponse:
    try:
        result = await service.submit_draft(
            draft_id,
            auth.user_id,
            request.reason,
            str(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _operation_response(result)


@semantic_model_router.post(
    "/api/admin/semantic-model/drafts/{draft_id}/review",
    response_model=SemanticOperationResponse,
)
async def review_semantic_draft_handler(
    draft_id: str,
    request: SemanticReviewRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_review)],
    service: Annotated[SemanticModelService, Depends(get_semantic_model_service)],
) -> SemanticOperationResponse:
    try:
        result = await service.review_draft(
            draft_id,
            request.decision,
            auth.user_id,
            request.reason,
            str(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _operation_response(result)


@semantic_model_router.post(
    "/api/admin/semantic-model/drafts/{draft_id}/publish",
    response_model=SemanticOperationResponse,
)
async def publish_semantic_draft_handler(
    draft_id: str,
    request: SemanticActionRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_publish)],
    service: Annotated[SemanticModelService, Depends(get_semantic_model_service)],
) -> SemanticOperationResponse:
    try:
        result = await service.publish_draft(
            draft_id,
            auth.user_id,
            request.reason,
            str(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _operation_response(result)


@semantic_model_router.get(
    "/api/admin/semantic-model/releases",
    response_model=SemanticReleaseListResponse,
)
async def list_semantic_releases_handler(
    service: Annotated[
        SemanticModelService, Depends(get_semantic_model_service)
    ] = None,
    _auth: Annotated[AuthContext, Depends(_require_read)] = None,
) -> SemanticReleaseListResponse:
    records = await service.list_releases()
    items = [SemanticReleaseResponse(**record) for record in records]
    return SemanticReleaseListResponse(items=items, total=len(items))


@semantic_model_router.get(
    "/api/admin/semantic-model/releases/{release_version}",
    response_model=SemanticReleaseResponse,
)
async def get_semantic_release_handler(
    release_version: str,
    service: Annotated[
        SemanticModelService, Depends(get_semantic_model_service)
    ] = None,
    _auth: Annotated[AuthContext, Depends(_require_read)] = None,
) -> SemanticReleaseResponse:
    record = await service.get_release(release_version)
    if record is None:
        raise HTTPException(status_code=404, detail="semantic release not found")
    return SemanticReleaseResponse(**record)


@semantic_model_router.post(
    "/api/admin/semantic-model/releases/{release_version}/rollback",
    response_model=SemanticOperationResponse,
)
async def rollback_semantic_release_handler(
    release_version: str,
    request: SemanticActionRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_rollback)],
    service: Annotated[SemanticModelService, Depends(get_semantic_model_service)],
) -> SemanticOperationResponse:
    try:
        result = await service.rollback(
            release_version,
            auth.user_id,
            request.reason,
            str(idempotency_key),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _operation_response(result)


def _operation_response(result: SemanticOperationResult) -> SemanticOperationResponse:
    return SemanticOperationResponse(
        operation_id=result.operation_id,
        status=result.status,
        draft_id=result.draft_id,
        release_version=result.release_version,
        error_code=result.error_code,
        issues=[
            {
                "code": issue.code,
                "path": issue.path,
                "message": issue.message,
                "severity": issue.severity,
            }
            for issue in result.issues
        ],
    )
