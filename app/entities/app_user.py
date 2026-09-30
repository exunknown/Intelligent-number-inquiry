"""应用侧用户领域对象。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ApplicationRole = Literal[
    "platform_admin",
    "metric_governor",
    "analyst",
    "auditor",
]
APP_ROLES: frozenset[str] = frozenset(
    {"platform_admin", "metric_governor", "analyst", "auditor"}
)


@dataclass(frozen=True)
class ApplicationUser:
    """应用侧用户及其观察到的身份角色。"""

    user_id: str
    username: str | None
    display_name: str | None
    email: str | None
    observed_roles: frozenset[str]
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    disabled_at: datetime | None
    disabled_by: str | None
    updated_at: datetime
    application_roles: frozenset[str]
