"""元数据 manifest 的校验、激活和回滚状态机。"""

import inspect
from collections.abc import Awaitable, Callable

from app.entities.metadata_release import MetadataReleaseManifest


class MetadataReleaseService:
    """编排发布状态，不直接依赖 MySQL/Qdrant/ES 客户端。"""

    def __init__(self, repository):
        self.repository = repository

    async def prepare(
        self,
        manifest: MetadataReleaseManifest,
        validator: Callable[[], object] | Callable[[], Awaitable[object]],
    ):
        """校验 manifest 并推进到 validated，不切换活动版本。"""

        existing = await self.repository.get(manifest.release_version)
        if existing is not None:
            existing_manifest = existing["manifest"]
            if existing_manifest.sha256() != manifest.sha256():
                raise ValueError("release version already has a different manifest")
            if existing["status"] == "active":
                return existing

        await self.repository.create_building(manifest)
        try:
            validation_result = validator()
            if inspect.isawaitable(validation_result):
                await validation_result
            await self.repository.mark_validated(manifest.release_version)
            return await self.repository.get(manifest.release_version)
        except Exception:
            await self.repository.mark_failed(
                manifest.release_version, "metadata_release_validation_failed"
            )
            raise

    async def activate_validated(self, release_version: str):
        """激活已完成校验的 manifest。"""

        return await self.repository.activate(release_version)

    async def mark_failed(self, release_version: str, error_code: str) -> None:
        """记录发布阶段失败，不改变已有活动版本。"""

        await self.repository.mark_failed(release_version, error_code)

    async def publish(
        self,
        manifest: MetadataReleaseManifest,
        validator: Callable[[], object] | Callable[[], Awaitable[object]],
    ):
        """校验并激活一个 manifest；校验失败绝不切换活动版本。"""

        prepared = await self.prepare(manifest, validator)
        if prepared is not None and prepared["status"] == "active":
            return prepared
        return await self.activate_validated(manifest.release_version)

    async def rollback(self, release_version: str):
        """只允许切回已经完成验证的历史版本。"""

        record = await self.repository.get(release_version)
        if record is None or record["status"] not in {"validated", "active"}:
            raise ValueError("release version is not validated")
        return await self.repository.activate(release_version)
