"""跨存储元数据发布的顺序提交与补偿。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.log import logger
from app.entities.metadata_release import MetadataReleaseManifest
from app.services.metadata_release_service import MetadataReleaseService


@dataclass(frozen=True)
class MetadataAliasBinding:
    """一个待切换的稳定 alias 及其 staging/旧目标。"""

    label: str
    repository: object
    target: str
    previous: str | None


class MetadataReleaseCoordinator:
    """编排 manifest、Qdrant 和 ES 的顺序提交，并在失败时补偿。"""

    def __init__(self, release_service: MetadataReleaseService):
        self.release_service = release_service

    async def publish(
        self,
        manifest: MetadataReleaseManifest,
        bindings: list[MetadataAliasBinding],
        validator,
    ):
        prepared = await self.release_service.prepare(manifest, validator)
        if prepared is not None and prepared["status"] == "active":
            return prepared

        switched: list[MetadataAliasBinding] = []
        attempted: list[MetadataAliasBinding] = []
        try:
            for binding in bindings:
                attempted.append(binding)
                await binding.repository.swap_alias(binding.target, binding.previous)
                switched.append(binding)
            return await self.release_service.activate_validated(
                manifest.release_version
            )
        except Exception:
            await self._compensate_aliases(attempted, switched)
            try:
                await self.release_service.mark_failed(
                    manifest.release_version, "metadata_release_commit_failed"
                )
            except Exception as mark_failed_error:
                logger.error(
                    "元数据发布失败状态写入失败 version={} error_type={}",
                    manifest.release_version,
                    type(mark_failed_error).__name__,
                )
            raise

    async def rollback(
        self,
        release_version: str,
        bindings: list[MetadataAliasBinding],
    ):
        """切换到已校验版本；激活失败时只补偿 alias，不污染目标状态。"""

        record = await self.release_service.repository.get(release_version)
        if record is None or record["status"] not in {"validated", "active"}:
            raise ValueError("release version is not validated")

        attempted: list[MetadataAliasBinding] = []
        try:
            for binding in bindings:
                if binding.target == binding.previous:
                    continue
                attempted.append(binding)
                await binding.repository.swap_alias(binding.target, binding.previous)
            return await self.release_service.activate_validated(release_version)
        except Exception:
            await self._compensate_aliases(attempted, [])
            raise

    async def _compensate_aliases(
        self,
        attempted: list[MetadataAliasBinding],
        switched: list[MetadataAliasBinding],
    ) -> None:
        switched_set = set(id(binding) for binding in switched)
        for binding in reversed(attempted):
            try:
                get_alias_target = getattr(binding.repository, "get_alias_target", None)
                if get_alias_target is None:
                    continue
                current = await get_alias_target()
                if current != binding.target and id(binding) not in switched_set:
                    continue
                await binding.repository.swap_alias(binding.previous, binding.target)
            except Exception as rollback_error:
                logger.error(
                    "元数据发布 alias 补偿失败 label={} error_type={}",
                    binding.label,
                    type(rollback_error).__name__,
                )


class SemanticModelReleaseCoordinator:
    """语义模型发布的显式阶段协调器。

    具体的 Cube 编译、Qdrant staging 和 MySQL 激活由调用方注入，避免服务层
    在缺少外部依赖时自行伪造发布成功。
    """

    def __init__(
        self,
        *,
        compile_model: Callable[[object], Awaitable[object]],
        stage_search_index: Callable[[object], Awaitable[object]],
        activate_release: Callable[[object, str, str], Awaitable[object]],
        rollback_release: Callable[[str, str, str], Awaitable[object]],
    ):
        self.compile_model = compile_model
        self.stage_search_index = stage_search_index
        self.activate_release = activate_release
        self.rollback_release = rollback_release

    async def publish(self, snapshot, actor_id: str, reason: str):
        """按编译、索引 staging、激活顺序发布一个完整快照。"""

        await self.compile_model(snapshot)
        await self.stage_search_index(snapshot)
        return await self.activate_release(snapshot, actor_id, reason)

    async def rollback(self, release_version: str, actor_id: str, reason: str):
        """回滚只通过已注入的激活步骤执行。"""

        return await self.rollback_release(release_version, actor_id, reason)
