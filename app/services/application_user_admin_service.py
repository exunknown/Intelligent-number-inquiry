"""应用用户管理服务。"""

from dataclasses import dataclass
from typing import Collection, Literal

from app.entities.app_user import APP_ROLES, ApplicationUser
from app.entities.auth import AuthContext, PermissionSnapshot
from app.entities.authz_policy import AuthzPolicy
from app.repositories.mysql.meta.app_user_repository import AppUserRepository
from app.repositories.mysql.meta.authz_policy_repository import AuthzPolicyRepository
from app.services.authorization_service import (
    AuthorizationService,
    AuthorizationUnavailableError,
)


class LastPlatformAdminError(Exception):
    """拒绝会移除最后一个有效平台管理员来源的变更。"""


@dataclass(frozen=True)
class ApplicationUserListResult:
    items: list[ApplicationUser]
    total: int


@dataclass(frozen=True)
class ApplicationUserDetail:
    user: ApplicationUser
    direct_policies: list[AuthzPolicy]
    permission_preview: PermissionSnapshot
    preview_roles: frozenset[str]


class ApplicationUserAdminService:
    """提供用户管理读写及最后平台管理员保护。"""

    def __init__(
        self,
        repository: AppUserRepository,
        policy_repository: AuthzPolicyRepository,
        authorization_service: AuthorizationService,
    ):
        self.repository = repository
        self.policy_repository = policy_repository
        self.authorization_service = authorization_service

    async def get_user(self, user_id: str) -> ApplicationUser | None:
        return await self.repository.get(user_id)

    async def list_users(
        self,
        *,
        query: str | None,
        status: str | None,
        role: str | None,
        limit: int,
        offset: int,
    ) -> ApplicationUserListResult:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if role is not None and role not in APP_ROLES:
            raise ValueError("unsupported application role")
        users, total = await self.repository.list_users(
            query=query,
            status=status,
            role=role,
            limit=limit,
            offset=offset,
        )
        return ApplicationUserListResult(items=users, total=total)

    async def get_user_detail(self, user_id: str) -> ApplicationUserDetail | None:
        user = await self.repository.get(user_id)
        if user is None:
            return None

        try:
            policies = await self.policy_repository.list_active()
            preview_roles = user.observed_roles | user.application_roles
            preview_auth = AuthContext(
                user_id=user.user_id,
                username=user.username,
                roles=preview_roles,
                token_id=None,
                issued_at=0,
                expires_at=0,
                keycloak_roles=user.observed_roles,
                application_roles=user.application_roles,
                display_name=user.display_name,
                email=user.email,
            )
            permission_preview = await self.authorization_service.build_snapshot(
                preview_auth
            )
        except AuthorizationUnavailableError:
            raise
        except Exception as exc:
            raise AuthorizationUnavailableError(
                "authorization backend unavailable"
            ) from exc

        direct_policies = [
            policy for policy in policies if policy.subject == f"user:{user_id}"
        ]
        return ApplicationUserDetail(
            user=user,
            direct_policies=direct_policies,
            permission_preview=permission_preview,
            preview_roles=preview_roles,
        )

    async def set_status(
        self,
        *,
        user_id: str,
        status: Literal["active", "disabled"],
        reason: str,
        request_key: str,
        actor_user_id: str,
    ) -> ApplicationUser | None:
        clean_reason = self._validate_reason(reason)
        if status not in {"active", "disabled"}:
            raise ValueError("unsupported application user status")

        previous = await self.repository.replay_status(
            user_id=user_id, status=status, request_key=request_key
        )
        if previous is not None:
            return previous
        target = await self.repository.get(user_id)
        if target is None:
            return None
        candidates = await self.repository.lock_active_platform_admin_candidates()
        locked_target = self._locked_target(target, candidates)
        if (
            status == "disabled"
            and self._is_effective_platform_admin(locked_target)
            and len(candidates) <= 1
        ):
            raise LastPlatformAdminError(
                "cannot remove the last effective platform admin"
            )
        return await self.repository.set_status(
            user_id=user_id,
            status=status,
            actor_user_id=actor_user_id,
            request_key=request_key,
            reason=clean_reason,
        )

    async def replace_roles(
        self,
        *,
        user_id: str,
        roles: Collection[str],
        reason: str,
        request_key: str,
        actor_user_id: str,
    ) -> ApplicationUser | None:
        clean_reason = self._validate_reason(reason)
        desired_roles = frozenset(roles)
        if desired_roles - APP_ROLES:
            raise ValueError("unsupported application role")

        previous = await self.repository.replay_roles(
            user_id=user_id, roles=desired_roles, request_key=request_key
        )
        if previous is not None:
            return previous
        target = await self.repository.get(user_id)
        if target is None:
            return None
        candidates = await self.repository.lock_active_platform_admin_candidates()
        locked_target = self._locked_target(target, candidates)
        current_effective_admin = self._is_effective_platform_admin(locked_target)
        projected_effective_admin = locked_target.status == "active" and (
            "platform_admin" in locked_target.observed_roles
            or "platform_admin" in desired_roles
        )
        if (
            current_effective_admin
            and not projected_effective_admin
            and len(candidates) <= 1
        ):
            raise LastPlatformAdminError(
                "cannot remove the last effective platform admin"
            )
        return await self.repository.replace_roles(
            user_id=user_id,
            roles=desired_roles,
            actor_user_id=actor_user_id,
            request_key=request_key,
            reason=clean_reason,
        )

    @staticmethod
    def _validate_reason(reason: str) -> str:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("reason cannot be empty")
        return clean_reason

    @staticmethod
    def _is_effective_platform_admin(user: ApplicationUser) -> bool:
        return user.status == "active" and (
            "platform_admin" in user.observed_roles
            or "platform_admin" in user.application_roles
        )

    @staticmethod
    def _locked_target(
        target: ApplicationUser, candidates: Collection[ApplicationUser]
    ) -> ApplicationUser:
        for candidate in candidates:
            if candidate.user_id == target.user_id:
                return candidate
        return target
