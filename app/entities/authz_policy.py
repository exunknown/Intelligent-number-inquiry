"""版本化授权策略领域对象。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

AuthzEffect = Literal["allow", "deny"]
AuthzAction = Literal["execute", "read", "review", "manage"]

_SUBJECT_PREFIXES = ("user:", "role:")
_RESOURCE_PREFIXES = (
    "api:",
    "metric:",
    "table:",
    "column:",
    "row:department:",
)
_ACTIONS = frozenset({"execute", "read", "review", "manage"})
_EFFECTS = frozenset({"allow", "deny"})


def _validate_policy_fields(
    subject: str, resource: str, action: str, effect: str
) -> None:
    if "*" in subject or not subject.startswith(_SUBJECT_PREFIXES):
        raise ValueError("subject must use an exact user: or role: prefix")
    if "*" in resource or not resource.startswith(_RESOURCE_PREFIXES):
        raise ValueError("resource must use a supported exact prefix")
    if not subject.partition(":")[2] or not resource.rpartition(":")[2]:
        raise ValueError("subject and resource values cannot be empty")
    if action not in _ACTIONS:
        raise ValueError("unsupported authorization action")
    if effect not in _EFFECTS:
        raise ValueError("unsupported authorization effect")


@dataclass(frozen=True)
class AuthzPolicy:
    id: str
    subject: str
    resource: str
    action: AuthzAction
    effect: AuthzEffect
    version: int
    active: bool
    created_by: str
    created_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class AuthzPolicyCreate:
    subject: str
    resource: str
    action: AuthzAction
    effect: AuthzEffect
    reason: str

    def __post_init__(self) -> None:
        _validate_policy_fields(self.subject, self.resource, self.action, self.effect)
        if not self.reason.strip():
            raise ValueError("reason cannot be empty")


@dataclass(frozen=True)
class AuthzPolicyChange:
    id: str
    request_key: str
    operation: str
    policy_id: str
    actor_user_id: str
    reason: str
    before_json: dict | None
    after_json: dict
    created_at: datetime
