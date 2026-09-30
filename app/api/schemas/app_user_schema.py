"""应用用户管理接口模型。"""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas.authz_schema import AuthzPolicyResponse, PermissionPreviewResponse
from app.entities.app_user import ApplicationRole, ApplicationUserStatus


def _clean_reason(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("reason cannot be empty")
    return value


class ApplicationUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    username: str | None
    display_name: str | None
    email: str | None
    status: ApplicationUserStatus
    keycloak_roles: list[str]
    application_roles: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    disabled_at: datetime | None

    @field_validator("first_seen_at", "last_seen_at", "disabled_at")
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        """Meta MySQL 的无时区时间按 UTC 返回，供浏览器正确转换。"""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ApplicationUserListResponse(BaseModel):
    items: list[ApplicationUserSummary]
    total: int
    limit: int
    offset: int


class ApplicationUserStatusRequest(BaseModel):
    status: ApplicationUserStatus
    reason: str = Field(max_length=500)

    _validate_reason = field_validator("reason")(_clean_reason)


class ApplicationUserRolesRequest(BaseModel):
    roles: list[ApplicationRole]
    reason: str = Field(max_length=500)

    _validate_reason = field_validator("reason")(_clean_reason)


class UserListQuery(BaseModel):
    query: str | None = Field(default=None, max_length=255)
    status: ApplicationUserStatus | None = None
    role: ApplicationRole | None = None
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ApplicationUserMeResponse(BaseModel):
    user: ApplicationUserSummary
    can_manage_users: bool


class ApplicationUserDetailResponse(BaseModel):
    user: ApplicationUserSummary
    direct_policies: list[AuthzPolicyResponse]
    permission_preview: PermissionPreviewResponse
