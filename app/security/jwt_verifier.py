"""OIDC JWT 签名与声明校验。"""

import asyncio
import time
from collections.abc import Mapping
from typing import Any

import httpx
import jwt

from app.conf.app_config import AuthConfig
from app.entities.auth import AuthContext


class AuthenticationError(Exception):
    """访问令牌无法通过认证。"""


class OIDCJWTVerifier:
    """使用远程 JWKS 严格校验 RS256 访问令牌。"""

    def __init__(self, config: AuthConfig, client: httpx.AsyncClient):
        self.config = config
        self.client = client
        self._keys: dict[str, jwt.PyJWK] = {}
        self._cache_expires_at = 0.0
        self._refresh_lock = asyncio.Lock()

    async def verify(self, token: str) -> AuthContext:
        """校验令牌并返回只包含业务所需字段的身份对象。"""
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise AuthenticationError("invalid access token")

            selected_jwk = await self._get_key(kid)
            claims = jwt.decode(
                token,
                key=selected_jwk.key,
                algorithms=["RS256"],
                audience=self.config.audience,
                issuer=self.config.issuer,
                leeway=self.config.clock_skew_seconds,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            return self._to_auth_context(claims)
        except AuthenticationError:
            raise
        except (
            jwt.PyJWTError,
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise AuthenticationError("invalid access token") from exc

    async def _get_key(self, kid: str) -> jwt.PyJWK:
        now = time.monotonic()
        if not self._keys or now >= self._cache_expires_at:
            await self._refresh_keys(force=False)

        selected = self._keys.get(kid)
        if selected is None:
            await self._refresh_keys(force=True)
            selected = self._keys.get(kid)
        if selected is None:
            raise AuthenticationError("invalid access token")
        return selected

    async def _refresh_keys(self, *, force: bool) -> None:
        async with self._refresh_lock:
            now = time.monotonic()
            if not force and self._keys and now < self._cache_expires_at:
                return

            response = await self.client.get(self.config.jwks_url)
            response.raise_for_status()
            payload = response.json()
            raw_keys = payload.get("keys") if isinstance(payload, Mapping) else None
            if not isinstance(raw_keys, list):
                raise AuthenticationError("invalid access token")

            parsed: dict[str, jwt.PyJWK] = {}
            for raw_key in raw_keys:
                if not isinstance(raw_key, Mapping):
                    continue
                if raw_key.get("use") != "sig" or raw_key.get("alg") != "RS256":
                    continue
                kid = raw_key.get("kid")
                if isinstance(kid, str) and kid:
                    parsed[kid] = jwt.PyJWK.from_dict(dict(raw_key))
            if not parsed:
                raise AuthenticationError("invalid access token")

            self._keys = parsed
            self._cache_expires_at = now + self.config.jwks_cache_seconds

    @staticmethod
    def _to_auth_context(claims: Mapping[str, Any]) -> AuthContext:
        user_id = claims.get("sub")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        if not isinstance(user_id, str) or not user_id:
            raise AuthenticationError("invalid access token")
        if not isinstance(issued_at, int) or not isinstance(expires_at, int):
            raise AuthenticationError("invalid access token")

        realm_access = claims.get("realm_access")
        raw_roles = (
            realm_access.get("roles", []) if isinstance(realm_access, Mapping) else []
        )
        roles = frozenset(role for role in raw_roles if isinstance(role, str))
        username = claims.get("preferred_username")
        token_id = claims.get("jti")
        return AuthContext(
            user_id=user_id,
            username=username if isinstance(username, str) else None,
            roles=roles,
            token_id=token_id if isinstance(token_id, str) else None,
            issued_at=issued_at,
            expires_at=expires_at,
        )
