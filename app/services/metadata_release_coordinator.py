"""跨存储元数据发布的顺序提交与补偿。"""

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
