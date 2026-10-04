"""应用用户管理服务。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Awaitable, Callable, Collection, Literal, TypeVar

from sqlalchemy.exc import SQLAlchemyError

from app.entities.app_user import APP_ROLES, ApplicationUser
from app.entities.auth import AuthContext, PermissionSnapshot
from app.entities.authz_policy import AuthzPolicy
from app.entities.keycloak_user import (
    KeycloakUser,
    KeycloakUserCreate,
    KeycloakUserUpdate,
)
from app.repositories.mysql.meta.app_user_repository import AppUserRepository
from app.repositories.mysql.meta.authz_policy_repository import AuthzPolicyRepository
from app.services.application_user_service import (
    ApplicationUserRepositoryUnavailableError,
)
from app.services.authorization_service import (
    AuthorizationService,
    AuthorizationUnavailableError,
)
from app.services.keycloak_user_service import (
    KeycloakUserNotFoundError,
    KeycloakUserService,
    KeycloakUserServiceError,
)


class LastPlatformAdminError(Exception):
    """拒绝会移除最后一个有效平台管理员来源的变更。"""


_ResultT = TypeVar("_ResultT")


async def _user_repository_call(
    operation: Callable[..., Awaitable[_ResultT]], *args, **kwargs
) -> _ResultT:
    try:
        return await operation(*args, **kwargs)
    except SQLAlchemyError as exc:
        raise ApplicationUserRepositoryUnavailableError(
            "application user repository unavailable"
        ) from exc


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
        keycloak_user_service: KeycloakUserService | None = None,
    ):
        self.repository = repository
        self.policy_repository = policy_repository
        self.authorization_service = authorization_service
        self.keycloak_user_service = keycloak_user_service

    async def get_user(self, user_id: str) -> ApplicationUser | None:
        return await _user_repository_call(self.repository.get, user_id)

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
        if self.keycloak_user_service is None:
            users, total = await _user_repository_call(
                self.repository.list_users,
                query=query,
                status=status,
                role=role,
                limit=limit,
                offset=offset,
            )
            return ApplicationUserListResult(items=users, total=total)

        enabled = None
        if status == "active":
            enabled = True
        elif status == "disabled":
            enabled = False
        remote_users = await self.keycloak_user_service.list_users(
            query=query,
            enabled=enabled,
            first=offset,
            max=limit,
        )
        local_users = await _user_repository_call(
            self.repository.list_users_by_ids,
            [remote.user_id for remote in remote_users],
        )
        merged_users = [
            self._merge_keycloak_user(remote, local_users.get(remote.user_id))
            for remote in remote_users
        ]
        if role is not None:
            merged_users = [
                user for user in merged_users if role in user.application_roles
            ]
        return ApplicationUserListResult(items=merged_users, total=len(merged_users))

    async def get_user_detail(self, user_id: str) -> ApplicationUserDetail | None:
        local_user = await self.get_user(user_id)
        if self.keycloak_user_service is None:
            if local_user is None:
                return None
            user = local_user
        else:
            remote_user = await self._get_keycloak_user_or_none(user_id)
            if remote_user is None and local_user is None:
                return None
            user = (
                self._merge_keycloak_user(remote_user, local_user)
                if remote_user is not None
                else local_user
            )

        try:
            policies = await self.policy_repository.list_active(
                subject=f"user:{user_id}"
            )
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

        return ApplicationUserDetail(
            user=user,
            direct_policies=policies,
            permission_preview=permission_preview,
            preview_roles=preview_roles,
        )

    async def create_user(
        self,
        *,
        username: str,
        display_name: str,
        email: str,
        temporary_password: str,
        application_roles: Collection[str] | None,
        enabled: bool,
        request_key: str,
        actor_user_id: str,
    ) -> ApplicationUser:
        if self.keycloak_user_service is None:
            raise RuntimeError("keycloak user service is required")
        desired_roles = self._validate_application_roles(
            application_roles if application_roles is not None else ["analyst"]
        )
        created_user_id: str | None = None
        try:
            created_user_id = await self.keycloak_user_service.create_user(
                KeycloakUserCreate(
                    username=username,
                    display_name=display_name,
                    email=email,
                    temporary_password=temporary_password,
                    enabled=enabled,
                )
            )
            remote_user = await self.keycloak_user_service.get_user(created_user_id)
            await self._sync_keycloak_user(remote_user)
            user = await _user_repository_call(
                self.repository.replace_roles,
                user_id=created_user_id,
                roles=desired_roles,
                actor_user_id=actor_user_id,
                request_key=request_key,
                reason="创建用户",
            )
            if user is None:
                raise RuntimeError("created application user could not be loaded")
            return user
        except Exception:
            if created_user_id is not None:
                await self._try_delete_keycloak_user(created_user_id)
            raise

    async def update_user(
        self,
        *,
        user_id: str,
        display_name: str,
        email: str,
        temporary_password: str | None,
    ) -> ApplicationUser | None:
        if self.keycloak_user_service is None:
            raise RuntimeError("keycloak user service is required")
        remote_user = await self._get_keycloak_user_or_none(user_id)
        if remote_user is None:
            return None
        await self.keycloak_user_service.update_user(
            user_id,
            KeycloakUserUpdate(display_name=display_name, email=email),
        )
        if temporary_password is not None:
            await self.keycloak_user_service.reset_temporary_password(
                user_id, temporary_password
            )
        remote_user = await self.keycloak_user_service.get_user(user_id)
        return await self._sync_keycloak_user(remote_user)

    async def set_status(
        self,
        *,
        user_id: str,
        status: Literal["active", "disabled"],
        reason: str | None,
        request_key: str,
        actor_user_id: str,
    ) -> ApplicationUser | None:
        clean_reason = self._validate_status_reason(status, reason)
        if self.keycloak_user_service is None:
            return await self._set_status_local(
                user_id=user_id,
                status=status,
                reason=clean_reason,
                request_key=request_key,
                actor_user_id=actor_user_id,
            )

        previous = await _user_repository_call(
            self.repository.replay_status,
            user_id=user_id,
            status=status,
            request_key=request_key,
        )
        if previous is not None:
            return previous
        target = await self.get_user(user_id)
        if target is None:
            remote_user = await self._get_keycloak_user_or_none(user_id)
            if remote_user is None:
                return None
            target = await self._sync_keycloak_user(remote_user)
        candidates = await _user_repository_call(
            self.repository.lock_active_platform_admin_candidates
        )
        current_target = await _user_repository_call(
            self.repository.get_for_update, user_id
        )
        previous = await _user_repository_call(
            self.repository.replay_status,
            user_id=user_id,
            status=status,
            request_key=request_key,
            for_update=True,
        )
        if previous is not None:
            return previous
        if current_target is None:
            return None
        if (
            status == "disabled"
            and self._is_effective_platform_admin(current_target)
            and len(candidates) <= 1
        ):
            raise LastPlatformAdminError(
                "cannot remove the last effective platform admin"
            )

        previous_enabled = current_target.status == "active"
        await self.keycloak_user_service.set_enabled(user_id, status == "active")
        try:
            return await _user_repository_call(
                self.repository.set_status,
                user_id=user_id,
                status=status,
                actor_user_id=actor_user_id,
                request_key=request_key,
                reason=clean_reason,
            )
        except Exception:
            await self._try_restore_keycloak_enabled(user_id, previous_enabled)
            raise

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
        desired_roles = self._validate_application_roles(roles)

        previous = await _user_repository_call(
            self.repository.replay_roles,
            user_id=user_id,
            roles=desired_roles,
            request_key=request_key,
        )
        if previous is not None:
            return previous
        target = await self.get_user(user_id)
        if target is None:
            return None
        candidates = await _user_repository_call(
            self.repository.lock_active_platform_admin_candidates
        )
        current_target = await _user_repository_call(
            self.repository.get_for_update, user_id
        )
        previous = await _user_repository_call(
            self.repository.replay_roles,
            user_id=user_id,
            roles=desired_roles,
            request_key=request_key,
            for_update=True,
        )
        if previous is not None:
            return previous
        if current_target is None:
            return None
        current_effective_admin = self._is_effective_platform_admin(current_target)
        projected_effective_admin = current_target.status == "active" and (
            "platform_admin" in current_target.observed_roles
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
        return await _user_repository_call(
            self.repository.replace_roles,
            user_id=user_id,
            roles=desired_roles,
            actor_user_id=actor_user_id,
            request_key=request_key,
            reason=clean_reason,
        )

    async def _set_status_local(
        self,
        *,
        user_id: str,
        status: Literal["active", "disabled"],
        reason: str,
        request_key: str,
        actor_user_id: str,
    ) -> ApplicationUser | None:
        if status not in {"active", "disabled"}:
            raise ValueError("unsupported application user status")

        previous = await _user_repository_call(
            self.repository.replay_status,
            user_id=user_id,
            status=status,
            request_key=request_key,
        )
        if previous is not None:
            return previous
        target = await self.get_user(user_id)
        if target is None:
            return None
        candidates = await _user_repository_call(
            self.repository.lock_active_platform_admin_candidates
        )
        current_target = await _user_repository_call(
            self.repository.get_for_update, user_id
        )
        previous = await _user_repository_call(
            self.repository.replay_status,
            user_id=user_id,
            status=status,
            request_key=request_key,
            for_update=True,
        )
        if previous is not None:
            return previous
        if current_target is None:
            return None
        if (
            status == "disabled"
            and self._is_effective_platform_admin(current_target)
            and len(candidates) <= 1
        ):
            raise LastPlatformAdminError(
                "cannot remove the last effective platform admin"
            )
        return await _user_repository_call(
            self.repository.set_status,
            user_id=user_id,
            status=status,
            actor_user_id=actor_user_id,
            request_key=request_key,
            reason=reason,
        )

    async def _get_keycloak_user_or_none(self, user_id: str) -> KeycloakUser | None:
        if self.keycloak_user_service is None:
            return None
        try:
            return await self.keycloak_user_service.get_user(user_id)
        except KeycloakUserNotFoundError:
            return None

    async def _sync_keycloak_user(self, remote_user: KeycloakUser) -> ApplicationUser:
        return await _user_repository_call(
            self.repository.upsert_admin_user_snapshot,
            user_id=remote_user.user_id,
            username=remote_user.username,
            display_name=remote_user.display_name,
            email=remote_user.email,
            observed_roles=remote_user.keycloak_roles,
            status="active" if remote_user.enabled else "disabled",
        )

    async def _try_delete_keycloak_user(self, user_id: str) -> None:
        if self.keycloak_user_service is None:
            return
        try:
            await self.keycloak_user_service.delete_user(user_id)
        except KeycloakUserServiceError:
            return

    async def _try_restore_keycloak_enabled(self, user_id: str, enabled: bool) -> None:
        if self.keycloak_user_service is None:
            return
        try:
            await self.keycloak_user_service.set_enabled(user_id, enabled)
        except KeycloakUserServiceError:
            return

    @classmethod
    def _merge_keycloak_user(
        cls, remote_user: KeycloakUser, local_user: ApplicationUser | None
    ) -> ApplicationUser:
        timestamp = local_user.first_seen_at if local_user else remote_user.created_at
        if timestamp is None:
            timestamp = cls._now()
        return ApplicationUser(
            user_id=remote_user.user_id,
            username=remote_user.username,
            display_name=remote_user.display_name,
            email=remote_user.email,
            observed_roles=remote_user.keycloak_roles,
            status="active" if remote_user.enabled else "disabled",
            first_seen_at=local_user.first_seen_at if local_user else timestamp,
            last_seen_at=local_user.last_seen_at if local_user else timestamp,
            disabled_at=local_user.disabled_at if local_user else None,
            disabled_by=local_user.disabled_by if local_user else None,
            updated_at=local_user.updated_at if local_user else timestamp,
            application_roles=(
                local_user.application_roles if local_user else frozenset()
            ),
        )

    @staticmethod
    def _validate_status_reason(status: str, reason: str | None) -> str:
        if status not in {"active", "disabled"}:
            raise ValueError("unsupported application user status")
        if status == "active" and (reason is None or not reason.strip()):
            return "启用用户"
        return ApplicationUserAdminService._validate_reason(reason or "")

    @staticmethod
    def _validate_reason(reason: str) -> str:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("reason cannot be empty")
        return clean_reason

    @staticmethod
    def _validate_application_roles(roles: Collection[str]) -> frozenset[str]:
        desired_roles = frozenset(roles)
        if desired_roles - APP_ROLES:
            raise ValueError("unsupported application role")
        return desired_roles

    @staticmethod
    def _is_effective_platform_admin(user: ApplicationUser) -> bool:
        return user.status == "active" and (
            "platform_admin" in user.observed_roles
            or "platform_admin" in user.application_roles
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)
