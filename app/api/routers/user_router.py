"""应用用户管理接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.dependencies import (
    get_application_user_admin_service,
    get_authorization_service,
)
from app.api.schemas.app_user_schema import (
    ApplicationUserCreateRequest,
    ApplicationUserDetailResponse,
    ApplicationUserListResponse,
    ApplicationUserMeResponse,
    ApplicationUserRolesRequest,
    ApplicationUserStatusRequest,
    ApplicationUserSummary,
    ApplicationUserUpdateRequest,
    UserListQuery,
)
from app.api.schemas.authz_schema import AuthzPolicyResponse, PermissionPreviewResponse
from app.entities.app_user import ApplicationUser
from app.entities.auth import AuthContext
from app.repositories.mysql.meta.app_user_repository import (
    AppUserIdempotencyConflictError,
)
from app.security.dependencies import (
    get_application_auth_context,
    require_api_permission,
)
from app.services.application_user_admin_service import (
    ApplicationUserAdminService,
    LastPlatformAdminError,
)
from app.services.application_user_service import (
    ApplicationUserRepositoryUnavailableError,
)
from app.services.authorization_service import (
    AuthorizationService,
    AuthorizationUnavailableError,
)
from app.services.keycloak_user_service import KeycloakUserServiceError

user_router = APIRouter()
_require_manage = require_api_permission("api:users", "manage")


def _keycloak_exception(exc: KeycloakUserServiceError) -> HTTPException:
    status_code = 503
    if exc.code == "keycloak_user_conflict":
        status_code = 409
    elif exc.code == "keycloak_user_not_found":
        status_code = 404
    return HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
        },
    )


def _summary(user: ApplicationUser) -> ApplicationUserSummary:
    return ApplicationUserSummary(
        user_id=user.user_id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        status=user.status,
        keycloak_roles=sorted(user.observed_roles),
        application_roles=sorted(user.application_roles),
        first_seen_at=user.first_seen_at,
        last_seen_at=user.last_seen_at,
        disabled_at=user.disabled_at,
    )


def _detail_response(detail) -> ApplicationUserDetailResponse:
    snapshot = detail.permission_preview
    return ApplicationUserDetailResponse(
        user=_summary(detail.user),
        direct_policies=[
            AuthzPolicyResponse.model_validate(policy)
            for policy in detail.direct_policies
        ],
        permission_preview=PermissionPreviewResponse(
            user_id=detail.user.user_id,
            roles=sorted(detail.preview_roles),
            policy_version=snapshot.policy_version,
            allowed_metrics=sorted(snapshot.allowed_metrics),
            allowed_tables=sorted(snapshot.allowed_tables),
            allowed_columns=sorted(snapshot.allowed_columns),
            allowed_department_ids=sorted(snapshot.allowed_department_ids),
            sql_fallback_allowed=snapshot.sql_fallback_allowed,
        ),
    )


@user_router.get("/api/admin/users/me", response_model=ApplicationUserMeResponse)
async def get_current_user_handler(
    auth: Annotated[AuthContext, Depends(get_application_auth_context)],
    service: Annotated[
        ApplicationUserAdminService, Depends(get_application_user_admin_service)
    ],
    authorization_service: Annotated[
        AuthorizationService, Depends(get_authorization_service)
    ],
) -> ApplicationUserMeResponse:
    try:
        user = await service.get_user(auth.user_id)
    except ApplicationUserRepositoryUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="application user service unavailable"
        ) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="application user not found")
    try:
        can_manage_users = await authorization_service.authorize(
            auth, "api:users", "manage"
        )
        can_manage_semantic_model = await authorization_service.authorize(
            auth, "api:semantic-model", "read"
        )
    except AuthorizationUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="authorization service unavailable"
        ) from exc
    return ApplicationUserMeResponse(
        user=_summary(user),
        can_manage_users=can_manage_users,
        can_manage_semantic_model=can_manage_semantic_model,
    )


@user_router.post("/api/admin/users", response_model=ApplicationUserSummary)
async def create_user_handler(
    request: ApplicationUserCreateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_manage)],
    service: Annotated[
        ApplicationUserAdminService, Depends(get_application_user_admin_service)
    ],
) -> ApplicationUserSummary:
    try:
        user = await service.create_user(
            username=request.username,
            display_name=request.display_name,
            email=str(request.email),
            temporary_password=request.temporary_password,
            application_roles=request.application_roles,
            enabled=request.enabled,
            request_key=str(idempotency_key),
            actor_user_id=auth.user_id,
        )
    except ApplicationUserRepositoryUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="application user service unavailable"
        ) from exc
    except AppUserIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_conflict",
                "message": "idempotency key conflicts with an existing request",
            },
        ) from exc
    except KeycloakUserServiceError as exc:
        raise _keycloak_exception(exc) from exc
    return _summary(user)


@user_router.get("/api/admin/users", response_model=ApplicationUserListResponse)
async def list_users_handler(
    params: Annotated[UserListQuery, Depends()],
    _auth: Annotated[AuthContext, Depends(_require_manage)],
    service: Annotated[
        ApplicationUserAdminService, Depends(get_application_user_admin_service)
    ],
) -> ApplicationUserListResponse:
    try:
        result = await service.list_users(
            query=params.query,
            status=params.status,
            role=params.role,
            limit=params.limit,
            offset=params.offset,
        )
    except ApplicationUserRepositoryUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="application user service unavailable"
        ) from exc
    except KeycloakUserServiceError as exc:
        raise _keycloak_exception(exc) from exc
    return ApplicationUserListResponse(
        items=[_summary(user) for user in result.items],
        total=result.total,
        limit=params.limit,
        offset=params.offset,
    )


@user_router.get(
    "/api/admin/users/{user_id}", response_model=ApplicationUserDetailResponse
)
async def get_user_detail_handler(
    user_id: str,
    _auth: Annotated[AuthContext, Depends(_require_manage)],
    service: Annotated[
        ApplicationUserAdminService, Depends(get_application_user_admin_service)
    ],
) -> ApplicationUserDetailResponse:
    try:
        detail = await service.get_user_detail(user_id)
    except ApplicationUserRepositoryUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="application user service unavailable"
        ) from exc
    except AuthorizationUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="authorization service unavailable"
        ) from exc
    except KeycloakUserServiceError as exc:
        raise _keycloak_exception(exc) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="application user not found")
    return _detail_response(detail)


@user_router.patch("/api/admin/users/{user_id}", response_model=ApplicationUserSummary)
async def update_user_handler(
    user_id: str,
    request: ApplicationUserUpdateRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_manage)],
    service: Annotated[
        ApplicationUserAdminService, Depends(get_application_user_admin_service)
    ],
) -> ApplicationUserSummary:
    try:
        user = await service.update_user(
            user_id=user_id,
            display_name=request.display_name,
            email=str(request.email),
            temporary_password=request.temporary_password,
            request_key=str(idempotency_key),
            actor_user_id=auth.user_id,
        )
    except ApplicationUserRepositoryUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="application user service unavailable"
        ) from exc
    except AppUserIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_conflict",
                "message": "idempotency key conflicts with an existing request",
            },
        ) from exc
    except KeycloakUserServiceError as exc:
        raise _keycloak_exception(exc) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="application user not found")
    return _summary(user)


@user_router.patch(
    "/api/admin/users/{user_id}/status", response_model=ApplicationUserSummary
)
async def update_user_status_handler(
    user_id: str,
    request: ApplicationUserStatusRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_manage)],
    service: Annotated[
        ApplicationUserAdminService, Depends(get_application_user_admin_service)
    ],
) -> ApplicationUserSummary:
    try:
        user = await service.set_status(
            user_id=user_id,
            status=request.status,
            reason=request.reason,
            request_key=str(idempotency_key),
            actor_user_id=auth.user_id,
        )
    except ApplicationUserRepositoryUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="application user service unavailable"
        ) from exc
    except KeycloakUserServiceError as exc:
        raise _keycloak_exception(exc) from exc
    except LastPlatformAdminError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "last_platform_admin",
                "message": "cannot remove the last platform admin",
            },
        ) from exc
    except AppUserIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_conflict",
                "message": "idempotency key conflicts with an existing request",
            },
        ) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="application user not found")
    return _summary(user)


@user_router.put(
    "/api/admin/users/{user_id}/roles", response_model=ApplicationUserSummary
)
async def replace_user_roles_handler(
    user_id: str,
    request: ApplicationUserRolesRequest,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    auth: Annotated[AuthContext, Depends(_require_manage)],
    service: Annotated[
        ApplicationUserAdminService, Depends(get_application_user_admin_service)
    ],
) -> ApplicationUserSummary:
    try:
        user = await service.replace_roles(
            user_id=user_id,
            roles=request.roles,
            reason=request.reason,
            request_key=str(idempotency_key),
            actor_user_id=auth.user_id,
        )
    except ApplicationUserRepositoryUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="application user service unavailable"
        ) from exc
    except LastPlatformAdminError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "last_platform_admin",
                "message": "cannot remove the last platform admin",
            },
        ) from exc
    except AppUserIdempotencyConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_conflict",
                "message": "idempotency key conflicts with an existing request",
            },
        ) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="application user not found")
    return _summary(user)
