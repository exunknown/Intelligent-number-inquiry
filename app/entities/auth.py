"""认证与权限领域对象。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthContext:
    """由已验证访问令牌构造的调用者身份。"""

    user_id: str
    username: str | None
    roles: frozenset[str]
    token_id: str | None
    issued_at: int
    expires_at: int
    keycloak_roles: frozenset[str] = frozenset()
    application_roles: frozenset[str] = frozenset()
    display_name: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class PermissionSnapshot:
    """一次查询全程复用的不可变权限快照。"""

    policy_version: int
    allowed_metrics: frozenset[str]
    allowed_tables: frozenset[str]
    allowed_columns: frozenset[str]
    allowed_department_ids: frozenset[str]
    sql_fallback_allowed: bool


@dataclass(frozen=True)
class QueryPrincipal:
    """查询身份及其权限快照。"""

    auth: AuthContext
    permissions: PermissionSnapshot
