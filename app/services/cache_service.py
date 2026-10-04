"""问数缓存服务。"""

import hashlib
import json
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, is_dataclass
from typing import TypeVar

from app.conf.app_config import CacheConfig
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.cube_member import CubeMember
from app.entities.value_info import ValueInfo
from app.repositories.redis.cache_repository import CacheRepository

T = TypeVar("T")
E = TypeVar("E")
_CATEGORY_PATTERN = re.compile(r"^[a-z0-9_]+$")

_DEFAULT_CACHE_CONFIG = CacheConfig(
    enabled=True,
    embedding_ttl_seconds=604800,
    column_recall_ttl_seconds=600,
    cube_member_recall_ttl_seconds=600,
    value_recall_ttl_seconds=300,
    cube_catalog_ttl_seconds=300,
    metric_result_ttl_seconds=60,
    lock_ttl_seconds=10,
    lock_wait_seconds=0.2,
)


class CacheService:
    """封装缓存 Key、JSON 编解码和失败降级。"""

    namespace = "shopkeeper:cache"

    def __init__(
        self,
        repository: CacheRepository | None,
        config: CacheConfig | None = None,
    ):
        self.repository = repository
        self.config = config or _DEFAULT_CACHE_CONFIG

    def make_key(
        self,
        category: str,
        payload: object,
        schema_version: int = 1,
    ) -> str:
        """使用规范化 JSON 摘要生成缓存 Key，不暴露原始内容。"""

        if _CATEGORY_PATTERN.fullmatch(category) is None:
            raise ValueError("cache category must match ^[a-z0-9_]+$")
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{self.namespace}:{category}:v{schema_version}:{digest}"

    def make_lock_key(self, cache_key: str) -> str:
        """从数据缓存 Key 派生独立锁 Key。"""

        prefix = f"{self.namespace}:"
        if not cache_key.startswith(prefix):
            raise ValueError("cache lock can only be derived from cache keys")
        return f"shopkeeper:cache-lock:{cache_key.removeprefix(prefix)}"

    async def get_json(
        self,
        key: str,
        validator: Callable[[object], T],
    ) -> T | None:
        """读取并校验 JSON 缓存；坏值会被清理。"""

        if not self.config.enabled or self.repository is None:
            return None
        try:
            raw = await self.repository.get(key)
        except Exception:
            logger.warning("Cache get failed; falling back to source")
            return None
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            return validator(payload)
        except Exception:
            logger.warning("Invalid cache payload; deleting cached value")
            await self._delete_best_effort(key)
            return None

    async def set_json(
        self,
        key: str,
        payload: object,
        ttl_seconds: int,
    ) -> None:
        """以 JSON 写入缓存；失败不影响主链路。"""

        if not self.config.enabled or self.repository is None:
            return
        try:
            value = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            await self.repository.set(key, value, ttl_seconds)
        except Exception:
            logger.warning("Cache set failed; keeping source result")

    async def get_or_load_json(
        self,
        category: str,
        payload: object,
        ttl_seconds: int,
        loader: Callable[[], Awaitable[T]],
        validator: Callable[[object], T],
        *,
        schema_version: int = 1,
    ) -> tuple[T, bool]:
        """优先读缓存，miss 或坏值时回源加载并 best-effort 写回。"""

        key = self.make_key(category, payload, schema_version=schema_version)
        cached = await self.get_json(key, validator)
        if cached is not None:
            return cached, True

        value = await loader()
        await self.set_json(key, value, ttl_seconds)
        return value, False

    async def get_embedding(
        self,
        text: str,
        model_version: str,
        dimension: int,
        loader: Callable[[], Awaitable[list[float]]],
    ) -> tuple[list[float], bool]:
        """读取或生成 Embedding，并按模型版本和维度隔离。"""

        payload = {
            "model_version": model_version,
            "dimension": dimension,
            "text": normalize_embedding_text(text),
        }

        async def load_and_validate() -> list[float]:
            return _validate_embedding(await loader(), dimension)

        return await self.get_or_load_json(
            "embedding",
            payload,
            self.config.embedding_ttl_seconds,
            load_and_validate,
            lambda cached: _validate_embedding(cached, dimension),
        )

    async def get_column_recall(
        self,
        payload: object,
        loader: Callable[[], Awaitable[list[ColumnInfo]]],
    ) -> tuple[list[ColumnInfo], bool]:
        """读取或生成字段召回候选。"""

        return await self._get_or_load_entities(
            "column_recall",
            payload,
            self.config.column_recall_ttl_seconds,
            loader,
            ColumnInfo,
        )

    async def get_cube_member_recall(
        self,
        payload: object,
        loader: Callable[[], Awaitable[list[CubeMember]]],
    ) -> tuple[list[CubeMember], bool]:
        """读取或生成 Cube 成员召回候选。"""

        return await self._get_or_load_entities(
            "cube_member_recall",
            payload,
            self.config.cube_member_recall_ttl_seconds,
            loader,
            CubeMember,
        )

    async def get_value_recall(
        self,
        payload: object,
        loader: Callable[[], Awaitable[list[ValueInfo]]],
    ) -> tuple[list[ValueInfo], bool]:
        """读取或生成字段值召回候选。"""

        return await self._get_or_load_entities(
            "value_recall",
            payload,
            self.config.value_recall_ttl_seconds,
            loader,
            ValueInfo,
        )

    async def get_cube_catalog(
        self,
        payload: object,
        loader: Callable[[], Awaitable[list[CubeMember]]],
    ) -> tuple[list[CubeMember], bool]:
        """读取或生成 Cube 成员目录。"""

        return await self._get_or_load_entities(
            "cube_catalog",
            payload,
            self.config.cube_catalog_ttl_seconds,
            loader,
            CubeMember,
        )

    async def acquire_lock(self, key: str, ttl_seconds: int | None = None) -> bool:
        """获取短时锁；Redis 不可用时返回 False。"""

        if not self.config.enabled or self.repository is None:
            return False
        lock_key = self.make_lock_key(key)
        try:
            return await self.repository.acquire_lock(
                lock_key,
                ttl_seconds or self.config.lock_ttl_seconds,
            )
        except Exception:
            logger.warning("Cache lock failed; continuing without lock")
            return False

    async def _delete_best_effort(self, key: str) -> None:
        if self.repository is None:
            return
        try:
            await self.repository.delete(key)
        except Exception:
            logger.warning("Cache delete failed; ignoring stale value")

    async def _get_or_load_entities(
        self,
        category: str,
        payload: object,
        ttl_seconds: int,
        loader: Callable[[], Awaitable[list[E]]],
        entity_type: type[E],
    ) -> tuple[list[E], bool]:
        key = self.make_key(category, payload)
        cached = await self.get_json(
            key,
            lambda cached_payload: _validate_entity_list(
                cached_payload,
                entity_type,
            ),
        )
        if cached is not None:
            return cached, True

        value = await loader()
        _validate_loaded_entities(value, entity_type)
        await self.set_json(key, _serialize_entity_list(value), ttl_seconds)
        return value, False


def normalize_embedding_text(text: str) -> str:
    """规范化 Embedding Key 中的文本。"""

    return " ".join(text.strip().split())


def _validate_embedding(payload: object, dimension: int) -> list[float]:
    if not isinstance(payload, list) or len(payload) != dimension:
        raise ValueError("cached embedding dimension mismatch")
    embedding: list[float] = []
    for item in payload:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("cached embedding contains non-number")
        value = float(item)
        if not math.isfinite(value):
            raise ValueError("cached embedding contains non-finite number")
        embedding.append(value)
    return embedding


def _serialize_entity_list(values: list[object]) -> list[dict[str, object]]:
    serialized = []
    for value in values:
        if not is_dataclass(value):
            raise ValueError("cached entity must be a dataclass")
        serialized.append(asdict(value))
    return serialized


def _validate_entity_list(payload: object, entity_type: type[E]) -> list[E]:
    if not isinstance(payload, list):
        raise ValueError("cached entity payload must be a list")
    entities: list[E] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("cached entity item must be an object")
        entities.append(entity_type(**item))
    return entities


def _validate_loaded_entities(values: list[E], entity_type: type[E]) -> None:
    if not isinstance(values, list):
        raise ValueError("loaded entity payload must be a list")
    if not all(isinstance(value, entity_type) for value in values):
        raise ValueError("loaded entity type mismatch")
