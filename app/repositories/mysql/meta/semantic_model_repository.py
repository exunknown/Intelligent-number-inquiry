"""语义模型草稿和发布快照仓储。"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.semantic_model import (
    SemanticCube,
    SemanticDimensionDefinition,
    SemanticJoin,
    SemanticMeasureDefinition,
    SemanticMember,
    SemanticModelSnapshot,
)
from app.models.metadata_release import MetadataReleaseMySQL
from app.models.semantic_cube import SemanticCubeMySQL
from app.models.semantic_dimension_definition import SemanticDimensionDefinitionMySQL
from app.models.semantic_draft import SemanticModelChangeMySQL, SemanticModelDraftMySQL
from app.models.semantic_join import SemanticJoinMySQL
from app.models.semantic_measure_definition import SemanticMeasureDefinitionMySQL
from app.models.semantic_member import SemanticMemberMySQL


class SemanticModelRepository:
    """读写不可变发布快照和可编辑草稿。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    async def get_snapshot(self, release_version: str) -> SemanticModelSnapshot | None:
        cube_result = await self.session.execute(
            select(SemanticCubeMySQL).where(
                SemanticCubeMySQL.release_version == release_version
            )
        )
        join_result = await self.session.execute(
            select(SemanticJoinMySQL).where(
                SemanticJoinMySQL.release_version == release_version
            )
        )
        member_result = await self.session.execute(
            select(SemanticMemberMySQL).where(
                SemanticMemberMySQL.release_version == release_version
            )
        )
        measure_result = await self.session.execute(
            select(SemanticMeasureDefinitionMySQL).where(
                SemanticMeasureDefinitionMySQL.release_version == release_version
            )
        )
        dimension_result = await self.session.execute(
            select(SemanticDimensionDefinitionMySQL).where(
                SemanticDimensionDefinitionMySQL.release_version == release_version
            )
        )

        cubes = list(cube_result.scalars().all())
        joins = list(join_result.scalars().all())
        members = list(member_result.scalars().all())
        measures = {model.member_id: model for model in measure_result.scalars().all()}
        dimensions = {
            model.member_id: model for model in dimension_result.scalars().all()
        }
        if not cubes and not members:
            return None

        semantic_members = tuple(
            self._member_entity(
                model,
                measures.get(model.member_id),
                dimensions.get(model.member_id),
            )
            for model in members
        )
        return SemanticModelSnapshot(
            release_version=release_version,
            cubes=tuple(
                SemanticCube(
                    release_version=model.release_version,
                    cube_name=model.cube_name,
                    sql_table=model.sql_table,
                    title=model.title,
                    description=model.description,
                    public=model.public,
                )
                for model in cubes
            ),
            joins=tuple(
                SemanticJoin(
                    release_version=model.release_version,
                    cube_name=model.cube_name,
                    target_cube_name=model.target_cube_name,
                    sql_expression=model.sql_expression,
                    relationship=model.relationship,
                    editable=model.editable,
                )
                for model in joins
            ),
            members=semantic_members,
        )

    async def get_active_snapshot(self) -> SemanticModelSnapshot | None:
        result = await self.session.execute(
            select(MetadataReleaseMySQL.release_version)
            .where(
                MetadataReleaseMySQL.active.is_(True),
                MetadataReleaseMySQL.status == "active",
            )
            .order_by(MetadataReleaseMySQL.activated_at.desc())
            .limit(1)
        )
        release_version = result.scalar_one_or_none()
        if release_version is None:
            return None
        return await self.get_snapshot(release_version)

    async def create_draft(
        self,
        snapshot: SemanticModelSnapshot,
        created_by: str,
    ) -> str:
        draft_id = str(uuid4())
        now = self._now()
        self.session.add(
            SemanticModelDraftMySQL(
                draft_id=draft_id,
                release_version=snapshot.release_version,
                status="draft",
                snapshot_json=snapshot.to_dict(),
                created_by=created_by,
                updated_by=created_by,
                created_at=now,
                updated_at=now,
            )
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return draft_id

    async def get_draft(self, draft_id: str) -> SemanticModelSnapshot | None:
        model = await self.session.get(SemanticModelDraftMySQL, draft_id)
        if model is None:
            return None
        return SemanticModelSnapshot.from_dict(model.snapshot_json)

    async def get_draft_record(self, draft_id: str) -> dict | None:
        model = await self.session.get(SemanticModelDraftMySQL, draft_id)
        if model is None:
            return None
        return {
            "draft_id": model.draft_id,
            "snapshot": SemanticModelSnapshot.from_dict(model.snapshot_json),
            "status": model.status,
            "review_note": model.review_note,
            "updated_at": model.updated_at,
        }

    async def set_draft_status(
        self,
        draft_id: str,
        status: str,
        updated_by: str,
        review_note: str | None = None,
    ) -> None:
        result = await self.session.execute(
            select(SemanticModelDraftMySQL)
            .where(SemanticModelDraftMySQL.draft_id == draft_id)
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError("semantic model draft not found")
        model.status = status
        model.updated_by = updated_by
        model.review_note = review_note
        model.updated_at = self._now()
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def get_change_by_key(self, idempotency_key: str) -> dict | None:
        result = await self.session.execute(
            select(SemanticModelChangeMySQL)
            .where(SemanticModelChangeMySQL.idempotency_key == idempotency_key)
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return {
            "operation_id": model.change_id,
            "draft_id": model.draft_id or None,
            "action": model.action,
            "actor_id": model.actor_id,
            "reason": model.reason,
        }

    async def record_change(
        self,
        *,
        draft_id: str | None,
        action: str,
        actor_id: str,
        reason: str,
        idempotency_key: str,
    ) -> dict:
        change_id = str(uuid4())
        self.session.add(
            SemanticModelChangeMySQL(
                change_id=change_id,
                draft_id=draft_id or "",
                action=action,
                actor_id=actor_id,
                reason=reason,
                idempotency_key=idempotency_key,
                created_at=self._now(),
            )
        )
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_change_by_key(idempotency_key)
            if existing is None:
                raise
            return existing
        except Exception:
            await self.session.rollback()
            raise
        return {
            "operation_id": change_id,
            "draft_id": draft_id,
            "action": action,
            "actor_id": actor_id,
            "reason": reason,
        }

    async def list_releases(self) -> list[dict]:
        result = await self.session.execute(
            select(MetadataReleaseMySQL).order_by(
                MetadataReleaseMySQL.created_at.desc()
            )
        )
        return [self._release_record(model) for model in result.scalars().all()]

    async def get_release(self, release_version: str) -> dict | None:
        model = await self.session.get(MetadataReleaseMySQL, release_version)
        return self._release_record(model) if model is not None else None

    async def update_draft(
        self,
        draft_id: str,
        snapshot: SemanticModelSnapshot,
        updated_by: str,
    ) -> None:
        result = await self.session.execute(
            select(SemanticModelDraftMySQL)
            .where(SemanticModelDraftMySQL.draft_id == draft_id)
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise ValueError("semantic model draft not found")
        if model.status not in {"draft", "rejected"}:
            raise ValueError("published semantic model draft cannot be updated")
        model.release_version = snapshot.release_version
        model.snapshot_json = snapshot.to_dict()
        model.updated_by = updated_by
        model.updated_at = self._now()
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    @staticmethod
    def _member_entity(
        model: SemanticMemberMySQL,
        measure: SemanticMeasureDefinitionMySQL | None,
        dimension: SemanticDimensionDefinitionMySQL | None,
    ) -> SemanticMember:
        return SemanticMember(
            release_version=model.release_version,
            member_id=model.member_id,
            cube_name=model.cube_name,
            member_name=model.member_name,
            member_type=model.member_type,
            title=model.title,
            description=model.description,
            data_type=model.data_type,
            source_column_id=model.source_column_id,
            ai_context=model.ai_context,
            aliases=tuple(model.aliases_json or ()),
            filterable=model.filterable,
            groupable=model.groupable,
            status=model.status,
            measure=(
                SemanticMeasureDefinition(
                    expression=measure.expression,
                    aggregation_type=measure.aggregation_type,
                    dependency_members=tuple(measure.dependency_members_json or ()),
                )
                if measure is not None
                else None
            ),
            dimension=(
                SemanticDimensionDefinition(
                    dimension_type=dimension.dimension_type,
                    time_granularity=dimension.time_granularity,
                    primary_key=dimension.primary_key,
                )
                if dimension is not None
                else None
            ),
        )

    @staticmethod
    def _release_record(model: MetadataReleaseMySQL) -> dict:
        return {
            "release_version": model.release_version,
            "status": model.status,
            "active": model.active,
            "error_code": model.error_code,
        }
