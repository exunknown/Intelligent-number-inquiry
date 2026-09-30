"""FastAPI 认证与授权依赖。"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies import (
    get_application_user_service,
    get_authorization_service,
)
from app.clients.oidc_client_manager import get_oidc_client_manager
from app.conf.app_config import app_config
from app.entities.auth import AuthContext, PermissionSnapshot, QueryPrincipal
from app.security.jwt_verifier import AuthenticationError, OIDCJWTVerifier
from app.services.application_user_service import (
    ApplicationUserDisabledError,
    ApplicationUserRepositoryUnavailableError,
    ApplicationUserService,
)
from app.services.authorization_service import (
    AuthorizationService,
    AuthorizationUnavailableError,
)

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_oidc_jwt_verifier() -> OIDCJWTVerifier:
    manager = get_oidc_client_manager()
    if manager.client is None:
        raise RuntimeError("OIDC client has not been initialized")
    return OIDCJWTVerifier(app_config.auth, manager.client)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[OIDCJWTVerifier, Depends(get_oidc_jwt_verifier)],
) -> AuthContext:
    """验证 Bearer Token 并返回调用者身份。"""

    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()
    try:
        return await verifier.verify(credentials.credentials)
    except AuthenticationError as exc:
        raise _unauthorized() from exc


async def get_application_auth_context(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    service: Annotated[ApplicationUserService, Depends(get_application_user_service)],
) -> AuthContext:
    """在 JWT 身份上补充应用用户状态和应用角色。"""

    try:
        return await service.ensure_active_context(auth)
    except ApplicationUserDisabledError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "user_disabled", "message": "user disabled"},
        ) from exc
    except ApplicationUserRepositoryUnavailableError as exc:
        raise HTTPException(status_code=503, detail="user service unavailable") from exc


def require_api_permission(resource: str, action: str):
    """构造一个要求精确 API 权限的 FastAPI 依赖。"""

    async def dependency(
        auth: Annotated[AuthContext, Depends(get_application_auth_context)],
        authorization_service: Annotated[
            AuthorizationService, Depends(get_authorization_service)
        ],
    ) -> AuthContext:
        try:
            if not await authorization_service.authorize(auth, resource, action):
                raise HTTPException(status_code=403, detail="permission denied")
            return auth
        except AuthorizationUnavailableError as exc:
            raise HTTPException(
                status_code=503, detail="authorization service unavailable"
            ) from exc

    return dependency


async def build_permission_snapshot(
    auth: AuthContext, authorization_service: AuthorizationService
) -> PermissionSnapshot:
    try:
        return await authorization_service.build_snapshot(auth)
    except AuthorizationUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="authorization service unavailable"
        ) from exc


async def get_query_principal(
    auth: Annotated[
        AuthContext, Depends(require_api_permission("api:query", "execute"))
    ],
    authorization_service: Annotated[
        AuthorizationService, Depends(get_authorization_service)
    ],
) -> QueryPrincipal:
    """构造查询权限快照，并拒绝没有任何部门数据范围的调用者。"""

    permissions = await build_permission_snapshot(auth, authorization_service)
    if not permissions.allowed_department_ids:
        raise HTTPException(
            status_code=403,
            detail={"code": "no_data_scope", "message": "no department data scope"},
        )
    return QueryPrincipal(auth=auth, permissions=permissions)


def require_permission_snapshot(resource: str, action: str):
    """构造 API 授权后返回权限快照的依赖。"""

    permission_dependency = require_api_permission(resource, action)

    async def dependency(
        auth: Annotated[AuthContext, Depends(permission_dependency)],
        authorization_service: Annotated[
            AuthorizationService, Depends(get_authorization_service)
        ],
    ) -> PermissionSnapshot:
        return await build_permission_snapshot(auth, authorization_service)

    return dependency
