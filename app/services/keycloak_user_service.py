"""Keycloak 用户管理服务安全封装。"""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.clients.keycloak_admin_client import (
    KeycloakAdminClient,
    KeycloakAdminError,
    KeycloakAdminUnavailableError,
)
from app.entities.keycloak_user import (
    KeycloakUser,
    KeycloakUserCreate,
    KeycloakUserUpdate,
)


class KeycloakUserServiceError(Exception):
    """Keycloak 用户服务对 API 层暴露的稳定错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class KeycloakUserUnavailableError(KeycloakUserServiceError):
    """Keycloak 用户服务暂不可用。"""

    def __init__(self) -> None:
        super().__init__(
            "keycloak_user_unavailable",
            "Keycloak 用户服务暂不可用",
            retryable=True,
        )


class KeycloakUserConflictError(KeycloakUserServiceError):
    """Keycloak 用户已存在或状态冲突。"""

    def __init__(self) -> None:
        super().__init__(
            "keycloak_user_conflict",
            "Keycloak 用户已存在或状态冲突",
        )


class KeycloakUserNotFoundError(KeycloakUserServiceError):
    """Keycloak 用户不存在。"""

    def __init__(self) -> None:
        super().__init__("keycloak_user_not_found", "Keycloak 用户不存在")


_ResultT = TypeVar("_ResultT")


class KeycloakUserService:
    """把 Keycloak Admin Client 的异常收敛为安全稳定错误。"""

    def __init__(self, client: KeycloakAdminClient) -> None:
        self.client = client

    async def list_users(
        self,
        *,
        query: str | None,
        enabled: bool | None,
        first: int,
        max: int,
    ) -> list[KeycloakUser]:
        return await self._call(
            self.client.list_users,
            query=query,
            enabled=enabled,
            first=first,
            max=max,
        )

    async def get_user(self, user_id: str) -> KeycloakUser:
        return await self._call(self.client.get_user, user_id)

    async def create_user(self, payload: KeycloakUserCreate) -> str:
        return await self._call(self.client.create_user, payload)

    async def update_user(self, user_id: str, payload: KeycloakUserUpdate) -> None:
        await self._call(self.client.update_user, user_id, payload)

    async def set_enabled(self, user_id: str, enabled: bool) -> None:
        await self._call(self.client.set_enabled, user_id, enabled)

    async def reset_temporary_password(self, user_id: str, password: str) -> None:
        await self._call(self.client.reset_temporary_password, user_id, password)

    async def delete_user(self, user_id: str) -> None:
        await self._call(self.client.delete_user, user_id)

    async def _call(
        self,
        operation: Callable[..., Awaitable[_ResultT]],
        *args,
        **kwargs,
    ) -> _ResultT:
        try:
            return await operation(*args, **kwargs)
        except KeycloakAdminUnavailableError as exc:
            raise KeycloakUserUnavailableError() from exc
        except KeycloakAdminError as exc:
            if exc.code == "keycloak_user_conflict":
                raise KeycloakUserConflictError() from exc
            if exc.code == "keycloak_user_not_found":
                raise KeycloakUserNotFoundError() from exc
            raise KeycloakUserUnavailableError() from exc
