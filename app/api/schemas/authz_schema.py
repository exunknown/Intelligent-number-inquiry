"""授权策略管理接口模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuthzPolicyCreateRequest(BaseModel):
    subject: str = Field(pattern=r"^(user|role):[A-Za-z0-9_.:@-]+$")
    resource: str = Field(
        pattern=r"^(api|metric|table|column|row:department):[A-Za-z0-9_.:@-]+$"
    )
    action: Literal["execute", "read", "review", "manage"]
    effect: Literal["allow", "deny"]
    reason: str = Field(min_length=1, max_length=500)


class AuthzPolicyRevokeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AuthzPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    subject: str
    resource: str
    action: str
    effect: str
    version: int
    active: bool
    created_by: str
    created_at: datetime
    revoked_at: datetime | None


class AuthzPolicyListResponse(BaseModel):
    items: list[AuthzPolicyResponse]
    total: int


class PermissionPreviewResponse(BaseModel):
    user_id: str
    roles: list[str]
    policy_version: int
    allowed_metrics: list[str]
    allowed_tables: list[str]
    allowed_columns: list[str]
    allowed_department_ids: list[str]
    sql_fallback_allowed: bool
