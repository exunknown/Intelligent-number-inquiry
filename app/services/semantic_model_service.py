"""指标维度治理草稿、审核和发布服务。"""

from dataclasses import dataclass, field
from typing import Literal

from app.entities.semantic_model import SemanticMember, SemanticModelSnapshot
from app.services.semantic_model_validation import ValidationIssue

DraftAction = Literal[
    "create",
    "update",
    "submit",
    "review",
    "publish",
    "rollback",
]


@dataclass(frozen=True)
class SemanticOperationResult:
    """治理操作的稳定结果，便于 HTTP 重放和前端展示。"""

    operation_id: str
    status: str
    draft_id: str | None = None
    release_version: str | None = None
    error_code: str | None = None
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)


class SemanticModelService:
    """只通过仓储和发布协调器推进语义模型状态。"""

    def __init__(self, repository, validator=None, release_coordinator=None):
        self.repository = repository
        self.validator = validator
        self.release_coordinator = release_coordinator

    async def list_members(
        self,
        member_type: str = "all",
        q: str | None = None,
    ) -> list[SemanticMember]:
        snapshot = await self.repository.get_active_snapshot()
        if snapshot is None:
            return []
        normalized_query = q.strip().casefold() if q else ""
        return [
            member
            for member in snapshot.members
            if (member_type == "all" or member.member_type == member_type)
            and (
                not normalized_query
                or normalized_query
                in " ".join(
                    [
                        member.member_name,
                        member.title,
                        member.description,
                        *member.aliases,
                    ]
                ).casefold()
            )
        ]

    async def get_draft(self, draft_id: str):
        return await self.repository.get_draft_record(draft_id)

    async def list_releases(self):
        return await self.repository.list_releases()

    async def get_release(self, release_version: str):
        return await self.repository.get_release(release_version)

    async def get_release_snapshot(self, release_version: str):
        return await self.repository.get_snapshot(release_version)

    async def create_draft(
        self,
        snapshot: SemanticModelSnapshot,
        actor_id: str,
        reason: str,
        idempotency_key: str,
    ) -> SemanticOperationResult:
        replay = await self._replay(idempotency_key)
        if replay is not None:
            return replay
        draft_id = await self.repository.create_draft(snapshot, actor_id)
        return await self._record(
            draft_id, "create", actor_id, reason, idempotency_key, snapshot
        )

    async def update_draft(
        self,
        draft_id: str,
        snapshot: SemanticModelSnapshot,
        actor_id: str,
        reason: str,
        idempotency_key: str,
    ) -> SemanticOperationResult:
        replay = await self._replay(idempotency_key)
        if replay is not None:
            return replay
        await self.repository.update_draft(draft_id, snapshot, actor_id)
        return await self._record(
            draft_id, "update", actor_id, reason, idempotency_key, snapshot
        )

    async def validate_draft(
        self, draft_id: str, actor_id: str
    ) -> SemanticOperationResult:
        record = await self._require_draft(draft_id)
        issues = tuple(self._validate(record["snapshot"]))
        return SemanticOperationResult(
            operation_id=f"validation:{draft_id}",
            status="validated" if not issues else "invalid",
            draft_id=draft_id,
            release_version=record["snapshot"].release_version,
            error_code="semantic_model_validation_failed" if issues else None,
            issues=issues,
        )

    async def submit_draft(
        self,
        draft_id: str,
        actor_id: str,
        reason: str,
        idempotency_key: str,
    ) -> SemanticOperationResult:
        replay = await self._replay(idempotency_key)
        if replay is not None:
            return replay
        record = await self._require_draft(draft_id)
        issues = tuple(self._validate(record["snapshot"]))
        if issues:
            return self._failure(
                draft_id,
                record["snapshot"].release_version,
                "semantic_model_validation_failed",
                issues,
            )
        self._require_status(record, {"draft", "rejected"})
        await self.repository.set_draft_status(
            draft_id, "pending_review", actor_id, reason
        )
        return await self._record(
            draft_id,
            "submit",
            actor_id,
            reason,
            idempotency_key,
            record["snapshot"],
            status="pending_review",
        )

    async def review_draft(
        self,
        draft_id: str,
        decision: Literal["approved", "rejected"],
        actor_id: str,
        reason: str,
        idempotency_key: str,
    ) -> SemanticOperationResult:
        replay = await self._replay(idempotency_key)
        if replay is not None:
            return replay
        record = await self._require_draft(draft_id)
        self._require_status(record, {"pending_review"})
        status = "validated" if decision == "approved" else "rejected"
        await self.repository.set_draft_status(draft_id, status, actor_id, reason)
        return await self._record(
            draft_id,
            "review",
            actor_id,
            reason,
            idempotency_key,
            record["snapshot"],
            status=status,
        )

    async def publish_draft(
        self,
        draft_id: str,
        actor_id: str,
        reason: str,
        idempotency_key: str,
        *,
        can_publish: bool = True,
    ) -> SemanticOperationResult:
        if not can_publish:
            raise PermissionError("publish permission required")
        replay = await self._replay(idempotency_key)
        if replay is not None:
            return replay
        record = await self._require_draft(draft_id)
        self._require_status(record, {"validated"})
        issues = tuple(self._validate(record["snapshot"]))
        if issues:
            return self._failure(
                draft_id,
                record["snapshot"].release_version,
                "semantic_model_validation_failed",
                issues,
            )
        if self.release_coordinator is None:
            return self._failure(
                draft_id,
                record["snapshot"].release_version,
                "semantic_model_publish_not_ready",
            )
        try:
            publication = await self.release_coordinator.publish(
                record["snapshot"], actor_id, reason
            )
            if isinstance(publication, dict) and publication.get("status") != "active":
                return self._failure(
                    draft_id,
                    record["snapshot"].release_version,
                    "semantic_model_publish_failed",
                )
        except Exception:
            return self._failure(
                draft_id,
                record["snapshot"].release_version,
                "semantic_model_publish_failed",
            )
        await self.repository.set_draft_status(draft_id, "published", actor_id, reason)
        return await self._record(
            draft_id,
            "publish",
            actor_id,
            reason,
            idempotency_key,
            record["snapshot"],
            status="published",
        )

    async def rollback(
        self,
        release_version: str,
        actor_id: str,
        reason: str,
        idempotency_key: str,
    ) -> SemanticOperationResult:
        replay = await self._replay(idempotency_key)
        if replay is not None:
            return replay
        if self.release_coordinator is None:
            return SemanticOperationResult(
                operation_id=f"failed:rollback:{release_version}",
                status="failed",
                release_version=release_version,
                error_code="semantic_model_publish_not_ready",
            )
        await self.release_coordinator.rollback(release_version, actor_id, reason)
        return await self._record(
            None,
            "rollback",
            actor_id,
            reason,
            idempotency_key,
            None,
            release_version=release_version,
            status="active",
        )

    def _validate(self, snapshot: SemanticModelSnapshot) -> list[ValidationIssue]:
        if self.validator is None:
            from app.services.semantic_model_validation import SemanticModelValidator

            self.validator = SemanticModelValidator()
        return self.validator.validate(snapshot)

    async def _require_draft(self, draft_id: str) -> dict:
        record = await self.repository.get_draft_record(draft_id)
        if record is None:
            raise ValueError("semantic model draft not found")
        return record

    @staticmethod
    def _require_status(record: dict, allowed: set[str]) -> None:
        if record["status"] not in allowed:
            raise ValueError(
                f"invalid semantic model transition from {record['status']}"
            )

    async def _replay(self, idempotency_key: str):
        existing = await self.repository.get_change_by_key(idempotency_key)
        if existing is None:
            return None
        return self._result_from_change(existing)

    async def _record(
        self,
        draft_id: str | None,
        action: DraftAction,
        actor_id: str,
        reason: str,
        idempotency_key: str,
        snapshot: SemanticModelSnapshot | None,
        *,
        status: str = "accepted",
        release_version: str | None = None,
    ) -> SemanticOperationResult:
        change = await self.repository.record_change(
            draft_id=draft_id,
            action=action,
            actor_id=actor_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        return SemanticOperationResult(
            operation_id=change["operation_id"],
            status=status,
            draft_id=draft_id,
            release_version=release_version
            or (snapshot.release_version if snapshot else None),
        )

    @staticmethod
    def _failure(
        draft_id: str,
        release_version: str,
        error_code: str,
        issues: tuple[ValidationIssue, ...] = (),
    ) -> SemanticOperationResult:
        return SemanticOperationResult(
            operation_id=f"failed:{draft_id}",
            status="failed",
            draft_id=draft_id,
            release_version=release_version,
            error_code=error_code,
            issues=issues,
        )

    @staticmethod
    def _result_from_change(change: dict) -> SemanticOperationResult:
        return SemanticOperationResult(
            operation_id=change["operation_id"],
            status="replayed",
            draft_id=change.get("draft_id"),
            release_version=change.get("release_version"),
        )
