"""基于版本化策略与 PyCasbin 的授权服务。"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import casbin

from app.entities.auth import AuthContext, PermissionSnapshot
from app.entities.authz_policy import AuthzPolicy
from app.repositories.mysql.meta.authz_policy_repository import AuthzPolicyRepository


class AuthorizationError(Exception):
    """调用者不具备请求的权限。"""


class AuthorizationUnavailableError(Exception):
    """策略存储或判定引擎暂时不可用。"""


@dataclass(frozen=True)
class _PolicyCache:
    version: int
    enforcer: casbin.Enforcer
    policies: tuple[AuthzPolicy, ...]


class AuthorizationCacheState:
    """跨请求共享的策略快照，不持有数据库 Session。"""

    def __init__(self):
        self.cache: _PolicyCache | None = None
        self.reload_lock = asyncio.Lock()


def _subject_match(subjects: tuple[str, ...], policy_subject: str) -> bool:
    return policy_subject in subjects


class AuthorizationService:
    """按策略版本缓存 Casbin Enforcer，并生成请求级权限快照。"""

    def __init__(
        self,
        repository: AuthzPolicyRepository,
        model_path: Path | None = None,
        cache_state: AuthorizationCacheState | None = None,
    ):
        self.repository = repository
        self.model_path = model_path or (
            Path(__file__).parents[2] / "conf" / "authz_model.conf"
        )
        self._cache_state = cache_state or AuthorizationCacheState()

    async def authorize(self, auth: AuthContext, resource: str, action: str) -> bool:
        cache = await self._get_cache()
        subjects = self._subjects(auth)
        try:
            return bool(cache.enforcer.enforce(subjects, resource, action))
        except Exception as exc:
            raise AuthorizationUnavailableError(
                "authorization engine unavailable"
            ) from exc

    async def require(self, auth: AuthContext, resource: str, action: str) -> None:
        if not await self.authorize(auth, resource, action):
            raise AuthorizationError("permission denied")

    async def build_snapshot(self, auth: AuthContext) -> PermissionSnapshot:
        cache = await self._get_cache()
        subjects = frozenset(self._subjects(auth))
        applicable = tuple(
            policy for policy in cache.policies if policy.subject in subjects
        )

        async def allowed_values(prefix: str, action: str) -> frozenset[str]:
            resources = {
                policy.resource
                for policy in applicable
                if policy.resource.startswith(prefix) and policy.action == action
            }
            allowed = {
                resource.removeprefix(prefix)
                for resource in resources
                if await self.authorize(auth, resource, action)
            }
            return frozenset(allowed)

        return PermissionSnapshot(
            policy_version=cache.version,
            allowed_metrics=await allowed_values("metric:", "read"),
            allowed_tables=await allowed_values("table:", "read"),
            allowed_columns=await allowed_values("column:", "read"),
            allowed_department_ids=await allowed_values("row:department:", "read"),
            sql_fallback_allowed=await self.authorize(
                auth, "api:sql-fallback", "execute"
            ),
        )

    async def _get_cache(self) -> _PolicyCache:
        try:
            version = await self.repository.current_version()
            cache = self._cache_state.cache
            if cache is not None and cache.version == version:
                return cache

            async with self._cache_state.reload_lock:
                version = await self.repository.current_version()
                cache = self._cache_state.cache
                if cache is not None and cache.version == version:
                    return cache
                policies = tuple(await self.repository.list_active())
                enforcer = casbin.Enforcer(str(self.model_path))
                enforcer.add_function("subjectMatch", _subject_match)
                for policy in policies:
                    enforcer.add_policy(
                        policy.subject,
                        policy.resource,
                        policy.action,
                        policy.effect,
                    )
                cache = _PolicyCache(version, enforcer, policies)
                self._cache_state.cache = cache
                return cache
        except AuthorizationUnavailableError:
            raise
        except Exception as exc:
            raise AuthorizationUnavailableError(
                "authorization backend unavailable"
            ) from exc

    @staticmethod
    def _subjects(auth: AuthContext) -> tuple[str, ...]:
        return (
            f"user:{auth.user_id}",
            *(f"role:{role}" for role in sorted(auth.roles)),
        )
