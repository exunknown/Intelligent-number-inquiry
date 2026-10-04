"""应用侧用户及角色仓储。"""

from datetime import datetime, timezone
from typing import Collection, Literal
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.app_user import APP_ROLES, ApplicationUser
from app.models.app_user import AppUserMySQL
from app.models.app_user_change import AppUserChangeMySQL
from app.models.app_user_role import AppUserRoleMySQL


class AppUserIdempotencyConflictError(ValueError):
    """幂等键已绑定其他用户、操作或目标值。"""


class AppUserRepository:
    """在 Meta MySQL 中维护应用侧用户、角色和变更审计。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _validate_roles(roles: Collection[str]) -> frozenset[str]:
        normalized = frozenset(roles)
        unknown = normalized - APP_ROLES
        if unknown:
            raise ValueError(f"unsupported application role(s): {sorted(unknown)}")
        return normalized

    @staticmethod
    def _normalize_observed_roles(roles: Collection[str]) -> frozenset[str]:
        normalized: set[str] = set()
        for role in roles:
            if not isinstance(role, str):
                raise ValueError("observed roles must contain strings")
            if role:
                normalized.add(role)
        return frozenset(normalized)

    @staticmethod
    def _optional_value(value: str | None) -> str | None:
        return value if value else None

    async def upsert_observed(
        self,
        *,
        user_id: str,
        username: str | None,
        display_name: str | None,
        email: str | None,
        observed_roles: Collection[str],
    ) -> ApplicationUser:
        roles = sorted(self._normalize_observed_roles(observed_roles))
        now = self._now()
        values = {
            "user_id": user_id,
            "username": self._optional_value(username),
            "display_name": self._optional_value(display_name),
            "email": self._optional_value(email),
            "observed_roles_json": roles,
            "status": "active",
            "first_seen_at": now,
            "last_seen_at": now,
            "disabled_at": None,
            "disabled_by": None,
            "updated_at": now,
        }
        update_values = {
            "observed_roles_json": roles,
            "last_seen_at": now,
            "updated_at": now,
        }
        for field in ("username", "display_name", "email"):
            value = values[field]
            if value:
                update_values[field] = value

        statement = mysql_insert(AppUserMySQL).values(**values)
        statement = statement.on_duplicate_key_update(**update_values)
        try:
            await self.session.execute(statement)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        user = await self.get(user_id)
        if user is None:
            raise RuntimeError("upserted application user could not be loaded")
        return user

    async def upsert_admin_user_snapshot(
        self,
        *,
        user_id: str,
        username: str | None,
        display_name: str | None,
        email: str | None,
        observed_roles: Collection[str],
        status: Literal["active", "disabled"],
    ) -> ApplicationUser:
        if status not in {"active", "disabled"}:
            raise ValueError("unsupported application user status")
        roles = sorted(self._normalize_observed_roles(observed_roles))
        now = self._now()
        disabled_at = now if status == "disabled" else None
        values = {
            "user_id": user_id,
            "username": self._optional_value(username),
            "display_name": self._optional_value(display_name),
            "email": self._optional_value(email),
            "observed_roles_json": roles,
            "status": status,
            "first_seen_at": now,
            "last_seen_at": now,
            "disabled_at": disabled_at,
            "disabled_by": None,
            "updated_at": now,
        }
        update_values = {
            "username": values["username"],
            "display_name": values["display_name"],
            "email": values["email"],
            "observed_roles_json": roles,
            "status": status,
            "disabled_at": disabled_at,
            "disabled_by": None,
            "updated_at": now,
        }

        statement = mysql_insert(AppUserMySQL).values(**values)
        statement = statement.on_duplicate_key_update(**update_values)
        try:
            await self.session.execute(statement)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        user = await self.get(user_id)
        if user is None:
            raise RuntimeError("upserted application user could not be loaded")
        return user

    async def get(self, user_id: str) -> ApplicationUser | None:
        model, roles = await self._load_user_with_roles(user_id)
        return self._to_entity(model, roles) if model is not None else None

    async def get_for_update(self, user_id: str) -> ApplicationUser | None:
        """在当前事务中锁定并刷新目标用户与活动角色。"""
        model, roles = await self._load_user_with_roles(user_id, for_update=True)
        return self._to_entity(model, roles) if model is not None else None

    async def list_users(
        self,
        query: str | None,
        status: str | None,
        role: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ApplicationUser], int]:
        if role is not None:
            self._validate_roles((role,))
        conditions = []
        if query and query.strip():
            pattern = f"%{query.strip()}%"
            conditions.append(
                or_(
                    AppUserMySQL.user_id.ilike(pattern),
                    AppUserMySQL.username.ilike(pattern),
                    AppUserMySQL.display_name.ilike(pattern),
                    AppUserMySQL.email.ilike(pattern),
                )
            )
        if status is not None:
            conditions.append(AppUserMySQL.status == status)
        if role is not None:
            active_role_users = select(AppUserRoleMySQL.user_id).where(
                AppUserRoleMySQL.role_code == role,
                AppUserRoleMySQL.revoked_at.is_(None),
            )
            conditions.append(AppUserMySQL.user_id.in_(active_role_users))

        count_result = await self.session.execute(
            select(func.count()).select_from(AppUserMySQL).where(*conditions)
        )
        total = int(count_result.scalar_one())
        user_result = await self.session.execute(
            select(AppUserMySQL)
            .where(*conditions)
            .order_by(AppUserMySQL.last_seen_at.desc(), AppUserMySQL.user_id)
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        models = list(user_result.scalars().all())
        if not models:
            return [], total

        roles_result = await self.session.execute(
            select(AppUserRoleMySQL).where(
                AppUserRoleMySQL.user_id.in_([model.user_id for model in models]),
                AppUserRoleMySQL.revoked_at.is_(None),
            )
        )
        role_map: dict[str, set[str]] = {}
        for role_model in roles_result.scalars().all():
            role_map.setdefault(role_model.user_id, set()).add(role_model.role_code)
        return [
            self._to_entity(model, role_map.get(model.user_id, set()))
            for model in models
        ], total

    async def list_users_by_ids(
        self, user_ids: Collection[str]
    ) -> dict[str, ApplicationUser]:
        ordered_ids = list(dict.fromkeys(user_ids))
        if not ordered_ids:
            return {}

        user_result = await self.session.execute(
            select(AppUserMySQL).where(AppUserMySQL.user_id.in_(ordered_ids))
        )
        models = list(user_result.scalars().all())
        if not models:
            return {}

        roles_result = await self.session.execute(
            select(AppUserRoleMySQL).where(
                AppUserRoleMySQL.user_id.in_([model.user_id for model in models]),
                AppUserRoleMySQL.revoked_at.is_(None),
            )
        )
        role_map: dict[str, set[str]] = {}
        for role_model in roles_result.scalars().all():
            role_map.setdefault(role_model.user_id, set()).add(role_model.role_code)
        return {
            model.user_id: self._to_entity(model, role_map.get(model.user_id, set()))
            for model in models
        }

    async def get_active_roles(self, user_id: str) -> frozenset[str]:
        result = await self.session.execute(
            select(AppUserRoleMySQL.role_code).where(
                AppUserRoleMySQL.user_id == user_id,
                AppUserRoleMySQL.revoked_at.is_(None),
            )
        )
        return frozenset(result.scalars().all())

    async def lock_active_platform_admin_candidates(self) -> list[ApplicationUser]:
        """锁定当前活动且拥有有效平台管理员角色的用户和角色行。

        该方法只建立并持有当前事务中的行锁，不提交事务；调用方应在同一
        事务内完成最后平台管理员保护判断及后续变更。
        """
        application_platform_admin = (
            select(1)
            .where(
                AppUserRoleMySQL.user_id == AppUserMySQL.user_id,
                AppUserRoleMySQL.role_code == "platform_admin",
                AppUserRoleMySQL.revoked_at.is_(None),
            )
            .exists()
        )
        user_result = await self.session.execute(
            select(AppUserMySQL)
            .where(
                AppUserMySQL.status == "active",
                or_(
                    func.json_contains(
                        AppUserMySQL.observed_roles_json,
                        '"platform_admin"',
                    )
                    == 1,
                    application_platform_admin,
                ),
            )
            .order_by(AppUserMySQL.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        models_by_id = {model.user_id: model for model in user_result.scalars().all()}
        if not models_by_id:
            return []

        role_result = await self.session.execute(
            select(AppUserRoleMySQL)
            .where(
                AppUserRoleMySQL.user_id.in_(list(models_by_id)),
                AppUserRoleMySQL.revoked_at.is_(None),
            )
            .order_by(AppUserRoleMySQL.user_id, AppUserRoleMySQL.role_code)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        role_map: dict[str, set[str]] = {}
        for role_model in role_result.scalars().all():
            role_map.setdefault(role_model.user_id, set()).add(role_model.role_code)
        # 外层行锁不传播到 EXISTS 子查询；只计数当前锁定并刷新的有效来源。
        return [
            self._to_entity(model, role_map.get(model.user_id, set()))
            for model in models_by_id.values()
            if model.status == "active"
            and (
                "platform_admin" in model.observed_roles_json
                or "platform_admin" in role_map.get(model.user_id, set())
            )
        ]

    async def replay_create_user(
        self,
        *,
        username: str,
        display_name: str,
        email: str,
        status: Literal["active", "disabled"],
        roles: Collection[str],
        password_fingerprint: str,
        request_key: str,
    ) -> ApplicationUser | None:
        desired_roles = self._validate_roles(roles)
        try:
            previous = await self._create_idempotent_result(
                request_key,
                username=username,
                display_name=display_name,
                email=email,
                status=status,
                roles=desired_roles,
                password_fingerprint=password_fingerprint,
            )
        except Exception:
            await self.session.rollback()
            raise
        if previous is not None:
            await self.session.rollback()
        return previous

    async def replay_profile_update(
        self,
        *,
        user_id: str,
        display_name: str,
        email: str,
        password_fingerprint: str | None,
        request_key: str,
    ) -> ApplicationUser | None:
        try:
            previous = await self._profile_update_idempotent_result(
                request_key,
                user_id=user_id,
                display_name=display_name,
                email=email,
                password_fingerprint=password_fingerprint,
            )
        except Exception:
            await self.session.rollback()
            raise
        if previous is not None:
            await self.session.rollback()
        return previous

    async def create_admin_user_snapshot(
        self,
        *,
        user_id: str,
        username: str | None,
        display_name: str | None,
        email: str | None,
        observed_roles: Collection[str],
        status: Literal["active", "disabled"],
        roles: Collection[str],
        actor_user_id: str,
        request_key: str,
        reason: str,
        password_fingerprint: str,
    ) -> ApplicationUser:
        if status not in {"active", "disabled"}:
            raise ValueError("unsupported application user status")
        desired_roles = self._validate_roles(roles)
        observed = sorted(self._normalize_observed_roles(observed_roles))
        clean_reason = self._validate_reason(reason)
        try:
            previous = await self._create_idempotent_result(
                request_key,
                username=username,
                display_name=display_name,
                email=email,
                status=status,
                roles=desired_roles,
                password_fingerprint=password_fingerprint,
            )
            if previous is not None:
                await self.session.rollback()
                return previous
            model, current_role_models = await self._load_user_with_roles(
                user_id, for_update=True
            )
            before = self._snapshot(model, current_role_models) if model else None
            now = self._now()
            if model is None:
                model = AppUserMySQL(
                    user_id=user_id,
                    username=self._optional_value(username),
                    display_name=self._optional_value(display_name),
                    email=self._optional_value(email),
                    observed_roles_json=observed,
                    status=status,
                    first_seen_at=now,
                    last_seen_at=now,
                    disabled_at=now if status == "disabled" else None,
                    disabled_by=None,
                    updated_at=now,
                )
                self.session.add(model)
                current_roles = set()
            else:
                current_roles = {
                    role_model.role_code for role_model in current_role_models
                }
                model.username = self._optional_value(username)
                model.display_name = self._optional_value(display_name)
                model.email = self._optional_value(email)
                model.observed_roles_json = observed
                model.status = status
                model.last_seen_at = now
                model.disabled_at = now if status == "disabled" else None
                model.disabled_by = None
                model.updated_at = now
            for role_model in current_role_models:
                if role_model.role_code not in desired_roles:
                    role_model.revoked_at = now
            for role_code in sorted(desired_roles - current_roles):
                self.session.add(
                    AppUserRoleMySQL(
                        id=str(uuid4()),
                        user_id=user_id,
                        role_code=role_code,
                        assigned_by=actor_user_id,
                        assigned_at=now,
                        revoked_at=None,
                    )
                )
            after = self._snapshot(model, desired_roles)
            after["password_fingerprint"] = password_fingerprint
            self.session.add(
                self._change(
                    request_key=request_key,
                    user_id=user_id,
                    operation="create_user",
                    actor_user_id=actor_user_id,
                    reason=clean_reason,
                    before=before,
                    after=after,
                    created_at=now,
                )
            )
            await self.session.commit()
            return self._to_entity(model, desired_roles)
        except IntegrityError:
            await self.session.rollback()
            previous = await self._create_idempotent_result(
                request_key,
                username=username,
                display_name=display_name,
                email=email,
                status=status,
                roles=desired_roles,
                password_fingerprint=password_fingerprint,
            )
            if previous is not None:
                return previous
            raise
        except Exception:
            await self.session.rollback()
            raise

    async def update_admin_user_profile_snapshot(
        self,
        *,
        user_id: str,
        username: str | None,
        display_name: str | None,
        email: str | None,
        observed_roles: Collection[str],
        status: Literal["active", "disabled"],
        actor_user_id: str,
        request_key: str,
        reason: str,
        password_fingerprint: str | None,
    ) -> ApplicationUser:
        if status not in {"active", "disabled"}:
            raise ValueError("unsupported application user status")
        observed = sorted(self._normalize_observed_roles(observed_roles))
        clean_reason = self._validate_reason(reason)
        try:
            previous = await self._profile_update_idempotent_result(
                request_key,
                user_id=user_id,
                display_name=display_name,
                email=email,
                password_fingerprint=password_fingerprint,
            )
            if previous is not None:
                await self.session.rollback()
                return previous
            model, current_role_models = await self._load_user_with_roles(
                user_id, for_update=True
            )
            before = self._snapshot(model, current_role_models) if model else None
            now = self._now()
            if model is None:
                model = AppUserMySQL(
                    user_id=user_id,
                    username=self._optional_value(username),
                    display_name=self._optional_value(display_name),
                    email=self._optional_value(email),
                    observed_roles_json=observed,
                    status=status,
                    first_seen_at=now,
                    last_seen_at=now,
                    disabled_at=now if status == "disabled" else None,
                    disabled_by=None,
                    updated_at=now,
                )
                self.session.add(model)
                current_roles = set()
            else:
                current_roles = self._role_codes(current_role_models)
                model.username = self._optional_value(username)
                model.display_name = self._optional_value(display_name)
                model.email = self._optional_value(email)
                model.observed_roles_json = observed
                model.status = status
                model.last_seen_at = now
                model.disabled_at = now if status == "disabled" else None
                model.disabled_by = None
                model.updated_at = now
            after = self._snapshot(model, current_roles)
            after["password_fingerprint"] = password_fingerprint
            self.session.add(
                self._change(
                    request_key=request_key,
                    user_id=user_id,
                    operation="update_profile",
                    actor_user_id=actor_user_id,
                    reason=clean_reason,
                    before=before,
                    after=after,
                    created_at=now,
                )
            )
            await self.session.commit()
            return self._to_entity(model, current_roles)
        except IntegrityError:
            await self.session.rollback()
            previous = await self._profile_update_idempotent_result(
                request_key,
                user_id=user_id,
                display_name=display_name,
                email=email,
                password_fingerprint=password_fingerprint,
            )
            if previous is not None:
                return previous
            raise
        except Exception:
            await self.session.rollback()
            raise

    async def replay_status(
        self,
        *,
        user_id: str,
        status: Literal["active", "disabled"],
        request_key: str,
        for_update: bool = False,
    ) -> ApplicationUser | None:
        if status not in {"active", "disabled"}:
            raise ValueError("unsupported application user status")
        try:
            previous = await self._idempotent_result(
                request_key,
                user_id=user_id,
                expected_operations="enable" if status == "active" else "disable",
                expected_status=status,
                for_update=for_update,
            )
        except Exception:
            await self.session.rollback()
            raise
        if previous is not None:
            await self.session.rollback()
        return previous

    async def replay_roles(
        self,
        *,
        user_id: str,
        roles: Collection[str],
        request_key: str,
        for_update: bool = False,
    ) -> ApplicationUser | None:
        desired_roles = self._validate_roles(roles)
        try:
            previous = await self._idempotent_result(
                request_key,
                user_id=user_id,
                expected_operations={"assign_role", "revoke_role", "replace_roles"},
                expected_application_roles=desired_roles,
                for_update=for_update,
            )
        except Exception:
            await self.session.rollback()
            raise
        if previous is not None:
            await self.session.rollback()
        return previous

    async def set_status(
        self,
        *,
        user_id: str,
        status: Literal["active", "disabled"],
        actor_user_id: str,
        request_key: str,
        reason: str,
    ) -> ApplicationUser | None:
        if status not in {"active", "disabled"}:
            raise ValueError("unsupported application user status")
        clean_reason = self._validate_reason(reason)
        operation = "enable" if status == "active" else "disable"

        try:
            model, roles = await self._load_user_with_roles(user_id, for_update=True)
            previous = await self._idempotent_result(
                request_key,
                user_id=user_id,
                expected_operations=operation,
                expected_status=status,
            )
            if previous is not None:
                await self.session.rollback()
                return previous
            if model is None:
                return None
            before = self._snapshot(model, roles)
            now = self._now()
            model.status = status
            model.updated_at = now
            if status == "disabled":
                model.disabled_at = now
                model.disabled_by = actor_user_id
            else:
                model.disabled_at = None
                model.disabled_by = None
            after = self._snapshot(model, roles)
            self.session.add(
                self._change(
                    request_key=request_key,
                    user_id=user_id,
                    operation=operation,
                    actor_user_id=actor_user_id,
                    reason=clean_reason,
                    before=before,
                    after=after,
                    created_at=now,
                )
            )
            await self.session.commit()
            return self._to_entity(model, roles)
        except IntegrityError:
            await self.session.rollback()
            previous = await self._idempotent_result(
                request_key,
                user_id=user_id,
                expected_operations=operation,
                expected_status=status,
            )
            if previous is not None:
                return previous
            raise
        except Exception:
            await self.session.rollback()
            raise

    async def replace_roles(
        self,
        *,
        user_id: str,
        roles: Collection[str],
        actor_user_id: str,
        request_key: str,
        reason: str,
    ) -> ApplicationUser | None:
        desired_roles = self._validate_roles(roles)
        clean_reason = self._validate_reason(reason)

        try:
            model, current_role_models = await self._load_user_with_roles(
                user_id, for_update=True
            )
            current_roles = {role_model.role_code for role_model in current_role_models}
            added_roles = desired_roles - current_roles
            revoked_roles = current_roles - desired_roles
            operation = (
                "assign_role"
                if added_roles and not revoked_roles
                else "revoke_role"
                if revoked_roles and not added_roles
                else "replace_roles"
            )
            previous = await self._idempotent_result(
                request_key,
                user_id=user_id,
                expected_operations={
                    "assign_role",
                    "revoke_role",
                    "replace_roles",
                },
                expected_application_roles=desired_roles,
            )
            if previous is not None:
                await self.session.rollback()
                return previous
            if model is None:
                return None
            before = self._snapshot(model, current_roles)
            now = self._now()
            model.updated_at = now
            for role_model in current_role_models:
                if role_model.role_code not in desired_roles:
                    role_model.revoked_at = now
            for role_code in sorted(desired_roles - current_roles):
                self.session.add(
                    AppUserRoleMySQL(
                        id=str(uuid4()),
                        user_id=user_id,
                        role_code=role_code,
                        assigned_by=actor_user_id,
                        assigned_at=now,
                        revoked_at=None,
                    )
                )
            after = self._snapshot(model, desired_roles)
            self.session.add(
                self._change(
                    request_key=request_key,
                    user_id=user_id,
                    operation=operation,
                    actor_user_id=actor_user_id,
                    reason=clean_reason,
                    before=before,
                    after=after,
                    created_at=now,
                )
            )
            await self.session.commit()
            return self._to_entity(model, desired_roles)
        except IntegrityError:
            await self.session.rollback()
            previous = await self._idempotent_result(
                request_key,
                user_id=user_id,
                expected_operations={
                    "assign_role",
                    "revoke_role",
                    "replace_roles",
                },
                expected_application_roles=desired_roles,
            )
            if previous is not None:
                return previous
            raise
        except Exception:
            await self.session.rollback()
            raise

    async def _change_by_request_key(
        self, request_key: str, *, for_update: bool = False
    ) -> AppUserChangeMySQL | None:
        statement = select(AppUserChangeMySQL).where(
            AppUserChangeMySQL.request_key == request_key
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def _create_idempotent_result(
        self,
        request_key: str,
        *,
        username: str | None,
        display_name: str | None,
        email: str | None,
        status: str,
        roles: Collection[str],
        password_fingerprint: str,
    ) -> ApplicationUser | None:
        change = await self._change_by_request_key(request_key)
        if change is None:
            return None
        snapshot = change.after_json
        if change.operation != "create_user":
            raise AppUserIdempotencyConflictError(
                "request key is already used for another operation"
            )
        expected = {
            "username": self._optional_value(username),
            "display_name": self._optional_value(display_name),
            "email": self._optional_value(email),
            "status": status,
            "application_roles": sorted(self._validate_roles(roles)),
            "password_fingerprint": password_fingerprint,
        }
        for key, expected_value in expected.items():
            if snapshot.get(key) != expected_value:
                raise AppUserIdempotencyConflictError(
                    "request key target user does not match"
                )
        return self._snapshot_to_entity(snapshot)

    async def _profile_update_idempotent_result(
        self,
        request_key: str,
        *,
        user_id: str,
        display_name: str | None,
        email: str | None,
        password_fingerprint: str | None,
    ) -> ApplicationUser | None:
        change = await self._change_by_request_key(request_key)
        if change is None:
            return None
        snapshot = change.after_json
        if change.user_id != user_id or snapshot.get("user_id") != user_id:
            raise AppUserIdempotencyConflictError(
                "request key is already used for another user"
            )
        if change.operation != "update_profile":
            raise AppUserIdempotencyConflictError(
                "request key is already used for another operation"
            )
        expected = {
            "display_name": self._optional_value(display_name),
            "email": self._optional_value(email),
            "password_fingerprint": password_fingerprint,
        }
        for key, expected_value in expected.items():
            if snapshot.get(key) != expected_value:
                raise AppUserIdempotencyConflictError(
                    "request key target profile does not match"
                )
        return self._snapshot_to_entity(snapshot)

    async def _idempotent_result(
        self,
        request_key: str,
        *,
        user_id: str,
        expected_operations: str | Collection[str],
        expected_status: str | None = None,
        expected_application_roles: Collection[str] | None = None,
        for_update: bool = False,
    ) -> ApplicationUser | None:
        change = await self._change_by_request_key(request_key, for_update=for_update)
        if change is None:
            return None
        snapshot = change.after_json
        operations = (
            {expected_operations}
            if isinstance(expected_operations, str)
            else set(expected_operations)
        )
        if change.user_id != user_id or snapshot.get("user_id") != user_id:
            raise AppUserIdempotencyConflictError(
                "request key is already used for another user"
            )
        if change.operation not in operations:
            raise AppUserIdempotencyConflictError(
                "request key is already used for another operation"
            )
        if expected_status is not None and snapshot.get("status") != expected_status:
            raise AppUserIdempotencyConflictError(
                "request key target status does not match"
            )
        if expected_application_roles is not None and frozenset(
            snapshot.get("application_roles", [])
        ) != frozenset(expected_application_roles):
            raise AppUserIdempotencyConflictError(
                "request key target roles do not match"
            )
        return self._snapshot_to_entity(snapshot)

    async def _load_user_with_roles(
        self, user_id: str, *, for_update: bool = False
    ) -> tuple[AppUserMySQL | None, list[AppUserRoleMySQL]]:
        user_statement = select(AppUserMySQL).where(AppUserMySQL.user_id == user_id)
        role_statement = select(AppUserRoleMySQL).where(
            AppUserRoleMySQL.user_id == user_id,
            AppUserRoleMySQL.revoked_at.is_(None),
        )
        if for_update:
            user_statement = user_statement.with_for_update().execution_options(
                populate_existing=True
            )
            role_statement = role_statement.with_for_update().execution_options(
                populate_existing=True
            )
        user_result = await self.session.execute(user_statement)
        model = user_result.scalar_one_or_none()
        if model is None:
            return None, []
        role_result = await self.session.execute(role_statement)
        return model, list(role_result.scalars().all())

    @staticmethod
    def _validate_reason(reason: str) -> str:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("reason cannot be empty")
        return clean_reason

    @staticmethod
    def _snapshot(
        model: AppUserMySQL, roles: Collection[str | AppUserRoleMySQL]
    ) -> dict[str, object]:
        return {
            "user_id": model.user_id,
            "username": model.username,
            "display_name": model.display_name,
            "email": model.email,
            "observed_roles": sorted(model.observed_roles_json),
            "status": model.status,
            "first_seen_at": model.first_seen_at.isoformat(),
            "last_seen_at": model.last_seen_at.isoformat(),
            "disabled_at": (
                model.disabled_at.isoformat() if model.disabled_at else None
            ),
            "disabled_by": model.disabled_by,
            "updated_at": model.updated_at.isoformat(),
            "application_roles": sorted(AppUserRepository._role_codes(roles)),
        }

    @staticmethod
    def _snapshot_to_entity(snapshot: dict[str, object]) -> ApplicationUser:
        def as_datetime(value: object) -> datetime:
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(str(value))

        disabled_at = snapshot.get("disabled_at")
        return ApplicationUser(
            user_id=str(snapshot["user_id"]),
            username=snapshot.get("username"),
            display_name=snapshot.get("display_name"),
            email=snapshot.get("email"),
            observed_roles=frozenset(snapshot.get("observed_roles", [])),
            status=str(snapshot["status"]),
            first_seen_at=as_datetime(snapshot["first_seen_at"]),
            last_seen_at=as_datetime(snapshot["last_seen_at"]),
            disabled_at=(as_datetime(disabled_at) if disabled_at is not None else None),
            disabled_by=snapshot.get("disabled_by"),
            updated_at=as_datetime(snapshot["updated_at"]),
            application_roles=frozenset(snapshot.get("application_roles", [])),
        )

    @staticmethod
    def _change(
        *,
        request_key: str,
        user_id: str,
        operation: str,
        actor_user_id: str,
        reason: str,
        before: dict[str, object],
        after: dict[str, object],
        created_at: datetime,
    ) -> AppUserChangeMySQL:
        return AppUserChangeMySQL(
            id=str(uuid4()),
            request_key=request_key,
            user_id=user_id,
            operation=operation,
            actor_user_id=actor_user_id,
            reason=reason,
            before_json=before,
            after_json=after,
            created_at=created_at,
        )

    @staticmethod
    def _role_codes(roles: Collection[str | AppUserRoleMySQL]) -> frozenset[str]:
        return frozenset(
            role.role_code if isinstance(role, AppUserRoleMySQL) else role
            for role in roles
        )

    @staticmethod
    def _to_entity(
        model: AppUserMySQL, roles: Collection[str | AppUserRoleMySQL]
    ) -> ApplicationUser:
        return ApplicationUser(
            user_id=model.user_id,
            username=model.username,
            display_name=model.display_name,
            email=model.email,
            observed_roles=frozenset(model.observed_roles_json),
            status=model.status,
            first_seen_at=model.first_seen_at,
            last_seen_at=model.last_seen_at,
            disabled_at=model.disabled_at,
            disabled_by=model.disabled_by,
            updated_at=model.updated_at,
            application_roles=AppUserRepository._role_codes(roles),
        )
