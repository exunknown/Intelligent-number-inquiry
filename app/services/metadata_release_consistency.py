"""活动元数据 manifest、稳定 alias 与物理资源的一致性检查。"""

import inspect
from collections.abc import Awaitable, Callable

from app.services.metadata_release_coordinator import MetadataAliasBinding


class MetadataReleaseConsistencyService:
    """提供发布后和就绪探针使用的只读一致性校验。"""

    @staticmethod
    async def verify(
        record: dict | None,
        bindings: list[MetadataAliasBinding],
        resource_exists: Callable[[MetadataAliasBinding], bool | Awaitable[bool]],
    ) -> dict:
        if (
            record is None
            or record.get("status") != "active"
            or record.get("active") is not True
        ):
            raise ValueError("active metadata release is unavailable")

        for binding in bindings:
            current = await binding.repository.get_alias_target()
            if current != binding.target:
                raise ValueError(
                    f"{binding.label} alias target mismatch: "
                    f"expected={binding.target} actual={current}"
                )
            exists = resource_exists(binding)
            if inspect.isawaitable(exists):
                exists = await exists
            if not exists:
                raise ValueError(
                    f"{binding.label} physical resource is missing: {binding.target}"
                )

        return {
            "release_version": record["manifest"].release_version,
            "manifest_sha256": record.get("manifest_sha256"),
            "alias_count": len(bindings),
        }
