"""版本化授权策略持久化。"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.authz_policy import AuthzPolicy, AuthzPolicyCreate
from app.models.authz_policy import AuthzPolicyMySQL
from app.models.authz_policy_change import AuthzPolicyChangeMySQL
from app.models.authz_policy_version import AuthzPolicyVersionMySQL


class AuthzPolicyRepository:
    """读写策略、版本与幂等变更记录。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active(self, subject: str | None = None) -> list[AuthzPolicy]:
        statement = (
            select(AuthzPolicyMySQL)
            .where(AuthzPolicyMySQL.active.is_(True))
            .order_by(AuthzPolicyMySQL.version, AuthzPolicyMySQL.id)
        )
        if subject:
            statement = statement.where(AuthzPolicyMySQL.subject == subject)
        result = await self.session.execute(statement)
        return [self._to_entity(model) for model in result.scalars().all()]

    async def current_version(self) -> int:
        result = await self.session.execute(
            select(AuthzPolicyVersionMySQL.version).where(
                AuthzPolicyVersionMySQL.id == 1
            )
        )
        return int(result.scalar_one())

    async def create(
        self,
        command: AuthzPolicyCreate,
        request_key: str,
        actor_user_id: str,
    ) -> AuthzPolicy:
        previous = await self._idempotent_result(request_key)
        if previous is not None:
            return previous

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            version = await self._next_version()
            model = AuthzPolicyMySQL(
                id=str(uuid4()),
                subject=command.subject,
                resource=command.resource,
                action=command.action,
                effect=command.effect,
                version=version,
                active=True,
                created_by=actor_user_id,
                created_at=now,
                revoked_at=None,
            )
            self.session.add(model)
            self.session.add(
                AuthzPolicyChangeMySQL(
                    id=str(uuid4()),
                    request_key=request_key,
                    operation="create",
                    policy_id=model.id,
                    actor_user_id=actor_user_id,
                    reason=command.reason.strip(),
                    before_json=None,
                    after_json=self._snapshot(model),
                    created_at=now,
                )
            )
            await self.session.commit()
            return self._to_entity(model)
        except Exception:
            await self.session.rollback()
            raise

    async def revoke(
        self,
        policy_id: str,
        reason: str,
        request_key: str,
        actor_user_id: str,
    ) -> AuthzPolicy | None:
        previous = await self._idempotent_result(request_key)
        if previous is not None:
            return previous
        if not reason.strip():
            raise ValueError("reason cannot be empty")

        try:
            result = await self.session.execute(
                select(AuthzPolicyMySQL)
                .where(AuthzPolicyMySQL.id == policy_id)
                .with_for_update()
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            if not model.active:
                return self._to_entity(model)

            before = self._snapshot(model)
            model.version = await self._next_version()
            model.active = False
            model.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            after = self._snapshot(model)
            self.session.add(
                AuthzPolicyChangeMySQL(
                    id=str(uuid4()),
                    request_key=request_key,
                    operation="revoke",
                    policy_id=model.id,
                    actor_user_id=actor_user_id,
                    reason=reason.strip(),
                    before_json=before,
                    after_json=after,
                    created_at=model.revoked_at,
                )
            )
            await self.session.commit()
            return self._to_entity(model)
        except Exception:
            await self.session.rollback()
            raise

    async def _idempotent_result(self, request_key: str) -> AuthzPolicy | None:
        result = await self.session.execute(
            select(AuthzPolicyChangeMySQL).where(
                AuthzPolicyChangeMySQL.request_key == request_key
            )
        )
        change = result.scalar_one_or_none()
        if change is None:
            return None
        model = await self.session.get(AuthzPolicyMySQL, change.policy_id)
        if model is None:
            raise RuntimeError("idempotency record references a missing policy")
        return self._to_entity(model)

    async def _next_version(self) -> int:
        result = await self.session.execute(
            select(AuthzPolicyVersionMySQL)
            .where(AuthzPolicyVersionMySQL.id == 1)
            .with_for_update()
        )
        model = result.scalar_one()
        model.version += 1
        return model.version

    @staticmethod
    def _snapshot(model: AuthzPolicyMySQL) -> dict:
        return {
            "id": model.id,
            "subject": model.subject,
            "resource": model.resource,
            "action": model.action,
            "effect": model.effect,
            "version": model.version,
            "active": model.active,
            "created_by": model.created_by,
            "created_at": model.created_at.isoformat(),
            "revoked_at": model.revoked_at.isoformat() if model.revoked_at else None,
        }

    @staticmethod
    def _to_entity(model: AuthzPolicyMySQL) -> AuthzPolicy:
        return AuthzPolicy(
            id=model.id,
            subject=model.subject,
            resource=model.resource,
            action=model.action,
            effect=model.effect,
            version=model.version,
            active=model.active,
            created_by=model.created_by,
            created_at=model.created_at,
            revoked_at=model.revoked_at,
        )
