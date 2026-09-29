"""元数据 manifest 注册表仓储。"""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.metadata_release import MetadataReleaseManifest
from app.models.metadata_release import MetadataReleaseLockMySQL, MetadataReleaseMySQL


class MetadataReleaseRepository:
    """提供活动版本读取和发布状态的事务性持久化。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _record(model: MetadataReleaseMySQL) -> dict:
        return {
            "manifest": MetadataReleaseManifest(**model.manifest_json),
            "manifest_sha256": model.manifest_sha256,
            "status": model.status,
            "active": model.active,
            "error_code": model.error_code,
        }

    async def get(self, release_version: str) -> dict | None:
        model = await self.session.get(MetadataReleaseMySQL, release_version)
        return self._record(model) if model is not None else None

    async def get_active_version(self) -> str | None:
        result = await self.session.execute(
            select(MetadataReleaseMySQL.release_version)
            .where(
                MetadataReleaseMySQL.active.is_(True),
                MetadataReleaseMySQL.status == "active",
            )
            .order_by(MetadataReleaseMySQL.activated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _lock(self) -> None:
        result = await self.session.execute(
            select(MetadataReleaseLockMySQL)
            .where(MetadataReleaseLockMySQL.id == 1)
            .with_for_update()
        )
        if result.scalar_one_or_none() is None:
            raise RuntimeError("metadata release lock is not initialized")

    async def create_building(self, manifest: MetadataReleaseManifest) -> None:
        await self.session.rollback()
        async with self.session.begin():
            await self._lock()
            model = await self.session.get(
                MetadataReleaseMySQL, manifest.release_version
            )
            now = self._now()
            if model is None:
                model = MetadataReleaseMySQL(
                    release_version=manifest.release_version,
                    manifest_json=manifest.__dict__,
                    manifest_sha256=manifest.sha256(),
                    status="building",
                    active=False,
                    created_at=now,
                )
                self.session.add(model)
            else:
                model.status = "building"
                model.active = False
                model.error_code = None
                model.manifest_json = manifest.__dict__
                model.manifest_sha256 = manifest.sha256()

    async def mark_validated(self, release_version: str) -> None:
        await self.session.rollback()
        async with self.session.begin():
            await self._lock()
            model = await self.session.get(MetadataReleaseMySQL, release_version)
            if model is None or model.status != "building":
                raise ValueError("release version is not building")
            model.status = "validated"
            model.validated_at = self._now()
            model.error_code = None

    async def mark_failed(self, release_version: str, error_code: str) -> None:
        await self.session.rollback()
        async with self.session.begin():
            await self._lock()
            model = await self.session.get(MetadataReleaseMySQL, release_version)
            if model is not None:
                model.status = "failed"
                model.active = False
                model.error_code = error_code

    async def activate(self, release_version: str) -> dict:
        await self.session.rollback()
        async with self.session.begin():
            await self._lock()
            model = await self.session.get(MetadataReleaseMySQL, release_version)
            if model is None or model.status not in {"validated", "active"}:
                raise ValueError("release version is not validated")
            await self.session.execute(
                update(MetadataReleaseMySQL)
                .values(active=False)
                .where(MetadataReleaseMySQL.active.is_(True))
            )
            now = self._now()
            model.status = "active"
            model.active = True
            model.activated_at = now
            model.error_code = None
        return self._record(model)
