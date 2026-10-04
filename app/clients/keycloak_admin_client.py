"""Keycloak Admin REST 客户端。"""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote, unquote, urlparse

import httpx

from app.conf.keycloak_admin_config import KeycloakAdminConfig
from app.entities.keycloak_user import (
    KeycloakUser,
    KeycloakUserCreate,
    KeycloakUserUpdate,
)


class _HTTPClient(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> object: ...


class KeycloakAdminError(Exception):
    """Keycloak Admin API 安全错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


class KeycloakAdminUnavailableError(KeycloakAdminError):
    """Keycloak Admin API 暂不可用。"""

    def __init__(self, message: str = "Keycloak 管理服务暂不可用") -> None:
        super().__init__("keycloak_admin_unavailable", message, True)


class KeycloakAdminClient:
    """封装 Keycloak Service Account token 与用户管理 REST 调用。"""

    def __init__(
        self,
        config: KeycloakAdminConfig,
        http_client: _HTTPClient | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self.http_client = http_client or httpx.AsyncClient()
        self.clock = clock
        self._access_token: str | None = None
        self._token_refresh_at = 0.0

    async def close(self) -> None:
        """关闭内部创建的 HTTP 客户端。"""
        close = getattr(self.http_client, "aclose", None)
        if close is not None:
            await close()

    async def list_users(
        self,
        query: str | None,
        enabled: bool | None,
        first: int,
        max: int,
    ) -> list[KeycloakUser]:
        """查询 Keycloak 用户列表。"""
        params: dict[str, object] = {"first": first, "max": max}
        if query:
            params["search"] = query
        if enabled is not None:
            params["enabled"] = enabled

        data = await self._request("GET", self._admin_url("users"), params=params)
        if not isinstance(data, list):
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")
        return [
            await self._map_user_with_realm_roles(item)
            for item in data
            if isinstance(item, dict)
        ]

    async def count_users(self, query: str | None, enabled: bool | None) -> int:
        """查询 Keycloak 用户总数。"""
        params: dict[str, object] = {}
        if query:
            params["search"] = query
        if enabled is not None:
            params["enabled"] = enabled

        data = await self._request(
            "GET", self._admin_url("users", "count"), params=params
        )
        if isinstance(data, bool) or not isinstance(data, int) or data < 0:
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")
        return data

    async def get_user(self, user_id: str) -> KeycloakUser:
        """按 ID 获取 Keycloak 用户。"""
        data = await self._request("GET", self._admin_url("users", user_id))
        if not isinstance(data, dict):
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")
        return await self._map_user_with_realm_roles(data)

    async def get_realm_roles(self, user_id: str) -> frozenset[str]:
        """读取用户的 Realm 角色映射。"""
        data = await self._request(
            "GET",
            self._admin_url("users", user_id, "role-mappings", "realm", "composite"),
        )
        if not isinstance(data, list):
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")
        return frozenset(
            role["name"]
            for role in data
            if isinstance(role, dict) and isinstance(role.get("name"), str)
        )

    async def create_user(self, payload: KeycloakUserCreate) -> str:
        """创建 Keycloak 用户，并返回新用户 ID。"""
        response = await self._request_raw(
            "POST",
            self._admin_url("users"),
            json={
                "username": payload.username,
                "firstName": payload.display_name,
                "email": payload.email,
                "enabled": payload.enabled,
                "credentials": [
                    {
                        "type": "password",
                        "value": payload.temporary_password,
                        "temporary": True,
                    }
                ],
            },
        )
        user_id = self._extract_location_user_id(response.headers.get("Location"))
        if user_id is None:
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")
        return user_id

    async def update_user(self, user_id: str, payload: KeycloakUserUpdate) -> None:
        """更新 Keycloak 用户基础资料。"""
        body: dict[str, object] = {}
        if payload.display_name is not None:
            body["firstName"] = payload.display_name
        if payload.email is not None:
            body["email"] = payload.email
        await self._request_raw("PUT", self._admin_url("users", user_id), json=body)

    async def set_enabled(self, user_id: str, enabled: bool) -> None:
        """启用或停用 Keycloak 用户。"""
        await self._request_raw(
            "PUT",
            self._admin_url("users", user_id),
            json={"enabled": enabled},
        )

    async def reset_temporary_password(self, user_id: str, password: str) -> None:
        """重置临时密码，强制用户下次登录修改。"""
        await self._request_raw(
            "PUT",
            self._admin_url("users", user_id, "reset-password"),
            json={"type": "password", "value": password, "temporary": True},
        )

    async def delete_user(self, user_id: str) -> None:
        """删除 Keycloak 用户，用于创建流程补偿。"""
        await self._request_raw("DELETE", self._admin_url("users", user_id))

    async def _get_token(self) -> str:
        if self._access_token and self.clock() < self._token_refresh_at:
            return self._access_token

        response = await self._request_without_token(
            "POST",
            self._token_url(),
            data={
                "grant_type": "client_credentials",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
            },
        )
        token_data = self._read_json_object(response)
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 0)
        if not isinstance(access_token, str) or not access_token:
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")
        if isinstance(expires_in, bool) or not isinstance(expires_in, int | float):
            expires_in = 0

        self._access_token = access_token
        self._token_refresh_at = self.clock() + max(
            0.0, float(expires_in) - self.config.token_cache_skew_seconds
        )
        return access_token

    async def _request(self, method: str, url: str, **kwargs: object) -> object:
        response = await self._request_raw(method, url, **kwargs)
        if response.status_code == 204:
            return None
        return self._read_json(response)

    async def _request_raw(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        token = await self._get_token()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Authorization"] = f"Bearer {token}"
        return await self._send(method, url, headers=headers, **kwargs)

    async def _request_without_token(
        self,
        method: str,
        url: str,
        **kwargs: object,
    ) -> httpx.Response:
        return await self._send(method, url, **kwargs)

    async def _send(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        try:
            response = await self.http_client.request(
                method,
                url,
                timeout=self.config.timeout_seconds,
                **kwargs,
            )
        except httpx.TimeoutException:
            raise KeycloakAdminUnavailableError() from None
        except httpx.RequestError:
            raise KeycloakAdminUnavailableError() from None

        if not isinstance(response, httpx.Response) and not all(
            hasattr(response, name)
            for name in ("status_code", "is_success", "json", "headers")
        ):
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")

        if not response.is_success:
            raise self._map_response_error(response)
        return response

    def _token_url(self) -> str:
        return self._url(
            "realms",
            self.config.realm,
            "protocol",
            "openid-connect",
            "token",
        )

    def _admin_url(self, *segments: str) -> str:
        return self._url("admin", "realms", self.config.realm, *segments)

    def _url(self, *segments: str) -> str:
        encoded = "/".join(quote(segment, safe="") for segment in segments)
        return f"{self.config.base_url.rstrip('/')}/{encoded}"

    @staticmethod
    def _map_response_error(response: object) -> KeycloakAdminError:
        status_code = getattr(response, "status_code", None)
        if status_code == 404:
            return KeycloakAdminError(
                "keycloak_user_not_found",
                "Keycloak 用户不存在",
                False,
                status_code,
            )
        if status_code == 409:
            return KeycloakAdminError(
                "keycloak_user_conflict",
                "Keycloak 用户已存在或状态冲突",
                False,
                status_code,
            )
        if status_code in (401, 403):
            return KeycloakAdminError(
                "keycloak_admin_unauthorized",
                "Keycloak 管理服务认证失败",
                False,
                status_code,
            )
        if isinstance(status_code, int) and status_code >= 500:
            return KeycloakAdminUnavailableError()
        return KeycloakAdminError(
            "keycloak_admin_request_failed",
            "Keycloak 管理服务请求失败",
            False,
            status_code if isinstance(status_code, int) else None,
        )

    @staticmethod
    def _read_json(response: object) -> object:
        try:
            return response.json()
        except ValueError:
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常") from None

    @classmethod
    def _read_json_object(cls, response: object) -> dict:
        data = cls._read_json(response)
        if not isinstance(data, dict):
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")
        return data

    async def _map_user_with_realm_roles(self, data: dict) -> KeycloakUser:
        user = self._map_user(data)
        realm_roles = await self.get_realm_roles(user.user_id)
        return KeycloakUser(
            user_id=user.user_id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            enabled=user.enabled,
            created_at=user.created_at,
            keycloak_roles=user.keycloak_roles | realm_roles,
        )

    @staticmethod
    def _map_user(data: dict) -> KeycloakUser:
        user_id = data.get("id")
        if not isinstance(user_id, str) or not user_id:
            raise KeycloakAdminUnavailableError("Keycloak 管理服务响应异常")
        return KeycloakUser(
            user_id=user_id,
            username=_optional_string(data.get("username")),
            display_name=_display_name(data),
            email=_optional_string(data.get("email")),
            enabled=data.get("enabled") is not False,
            created_at=_created_at(data.get("createdTimestamp")),
            keycloak_roles=_string_set(data.get("realmRoles")),
        )

    @staticmethod
    def _extract_location_user_id(location: str | None) -> str | None:
        if not location:
            return None
        path = urlparse(location).path
        segment = path.rstrip("/").rsplit("/", 1)[-1]
        if not segment:
            return None
        return unquote(segment)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _display_name(data: dict) -> str | None:
    first_name = _optional_string(data.get("firstName"))
    if first_name:
        return first_name
    attributes = data.get("attributes")
    if isinstance(attributes, dict):
        for key in ("display_name", "displayName", "name"):
            values = attributes.get(key)
            if isinstance(values, list) and values and isinstance(values[0], str):
                return values[0]
            if isinstance(values, str):
                return values
    return None


def _created_at(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(float(value) / 1000, tz=UTC)


def _string_set(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str))
