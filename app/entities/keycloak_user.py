"""Keycloak 用户管理领域对象。"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class KeycloakUser:
    """Keycloak 用户快照。"""

    user_id: str
    username: str | None
    display_name: str | None
    email: str | None
    enabled: bool
    created_at: datetime | None
    keycloak_roles: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class KeycloakUserCreate:
    """创建 Keycloak 用户所需输入。"""

    username: str
    display_name: str
    email: str
    temporary_password: str
    enabled: bool = True


@dataclass(frozen=True)
class KeycloakUserUpdate:
    """更新 Keycloak 用户资料所需输入。"""

    display_name: str | None = None
    email: str | None = None
    temporary_password: str | None = None
