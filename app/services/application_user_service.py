"""应用用户认证建档、状态检查和角色合并服务。"""

from dataclasses import replace

from app.entities.app_user import ApplicationUser
from app.entities.auth import AuthContext
from app.repositories.mysql.meta.app_user_repository import AppUserRepository


class ApplicationUserDisabledError(Exception):
    """应用用户已被禁用。"""


class ApplicationUserRepositoryUnavailableError(Exception):
    """应用用户仓储暂时不可用。"""


class ApplicationUserService:
    """在 JWT 身份之上补充应用用户状态和应用角色。"""

    def __init__(self, repository: AppUserRepository):
        self.repository = repository

    async def ensure_active_context(self, auth: AuthContext) -> AuthContext:
        user = await self._upsert_observed(auth)
        if user.status != "active":
            raise ApplicationUserDisabledError("application user is disabled")
        return replace(
            auth,
            roles=auth.keycloak_roles | user.application_roles,
            application_roles=user.application_roles,
        )

    async def get_current_user(self, auth: AuthContext) -> ApplicationUser:
        user = await self._upsert_observed(auth)
        if user.status != "active":
            raise ApplicationUserDisabledError("application user is disabled")
        return user

    async def _upsert_observed(self, auth: AuthContext) -> ApplicationUser:
        try:
            return await self.repository.upsert_observed(
                user_id=auth.user_id,
                username=auth.username,
                display_name=auth.display_name,
                email=auth.email,
                observed_roles=auth.keycloak_roles,
            )
        except Exception as exc:
            raise ApplicationUserRepositoryUnavailableError(
                "application user repository unavailable"
            ) from exc
