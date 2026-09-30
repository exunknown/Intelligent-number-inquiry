"""授权策略管理与权限预览接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.dependencies import (
    get_app_user_repository,
    get_authorization_service,
    get_authz_policy_repository,
)
from app.api.schemas.authz_schema import (
    AuthzPolicyCreateRequest,
    AuthzPolicyListResponse,
    AuthzPolicyResponse,
    AuthzPolicyRevokeRequest,
    PermissionPreviewResponse,
)
from app.entities.auth import AuthContext
from app.entities.authz_policy import AuthzPolicyCreate
from app.repositories.mysql.meta.app_user_repository import AppUserRepository
from app.repositories.mysql.meta.authz_policy_repository import AuthzPolicyRepository
from app.security.dependencies import build_permission_snapshot, require_api_permission
from app.services.authorization_service import AuthorizationService

authz_router = APIRouter()
_require_manage = require_api_permission("api:authz-policies", "manage")


@authz_router.get("/api/admin/authz/policies", response_model=AuthzPolicyListResponse)
async def list_authz_policies_handler(
    auth: Annotated[AuthContext, Depends(_require_manage)],
    repository: Annotated[AuthzPolicyRepository, Depends(get_authz_policy_repository)],
    subject: str | None = Query(None, max_length=255),
    limit: int = Query(100, ge=1, le=200),
) -> AuthzPolicyListResponse:
    del auth
    policies = await repository.list_active(subject=subject)
    policies = policies[:limit]
    return AuthzPolicyListResponse(
        items=[AuthzPolicyResponse.model_validate(policy) for policy in policies],
        total=len(policies),
    )


@authz_router.post(
    "/api/admin/authz/policies", response_model=AuthzPolicyResponse, status_code=201
)
async def create_authz_policy_handler(
    request: AuthzPolicyCreateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_manage)],
    repository: Annotated[AuthzPolicyRepository, Depends(get_authz_policy_repository)],
) -> AuthzPolicyResponse:
    policy = await repository.create(
        AuthzPolicyCreate(
            subject=request.subject,
            resource=request.resource,
            action=request.action,
            effect=request.effect,
            reason=request.reason,
        ),
        request_key=str(idempotency_key),
        actor_user_id=auth.user_id,
    )
    return AuthzPolicyResponse.model_validate(policy)


@authz_router.delete(
    "/api/admin/authz/policies/{policy_id}", response_model=AuthzPolicyResponse
)
async def revoke_authz_policy_handler(
    policy_id: str,
    request: AuthzPolicyRevokeRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_manage)],
    repository: Annotated[AuthzPolicyRepository, Depends(get_authz_policy_repository)],
) -> AuthzPolicyResponse:
    policy = await repository.revoke(
        policy_id,
        request.reason,
        str(idempotency_key),
        auth.user_id,
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="authorization policy not found")
    return AuthzPolicyResponse.model_validate(policy)


@authz_router.get(
    "/api/admin/authz/users/{user_id}/permissions",
    response_model=PermissionPreviewResponse,
)
async def preview_user_permissions_handler(
    user_id: str,
    auth: Annotated[AuthContext, Depends(_require_manage)],
    authorization_service: Annotated[
        AuthorizationService, Depends(get_authorization_service)
    ],
    app_user_repository: Annotated[AppUserRepository, Depends(get_app_user_repository)],
    roles: Annotated[list[str] | None, Query()] = None,
) -> PermissionPreviewResponse:
    del auth
    observed_roles = frozenset()
    application_roles = frozenset()
    if roles is None:
        try:
            user = await app_user_repository.get(user_id)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="authorization service unavailable"
            ) from exc
        if user is not None:
            observed_roles = user.observed_roles
            application_roles = user.application_roles
        preview_roles = observed_roles | application_roles
    else:
        preview_roles = frozenset(roles)
    preview_auth = AuthContext(
        user_id=user_id,
        username=None,
        roles=preview_roles,
        token_id=None,
        issued_at=0,
        expires_at=0,
        keycloak_roles=observed_roles,
        application_roles=application_roles,
    )
    snapshot = await build_permission_snapshot(preview_auth, authorization_service)
    return PermissionPreviewResponse(
        user_id=user_id,
        roles=sorted(preview_auth.roles),
        policy_version=snapshot.policy_version,
        allowed_metrics=sorted(snapshot.allowed_metrics),
        allowed_tables=sorted(snapshot.allowed_tables),
        allowed_columns=sorted(snapshot.allowed_columns),
        allowed_department_ids=sorted(snapshot.allowed_department_ids),
        sql_fallback_allowed=snapshot.sql_fallback_allowed,
    )
