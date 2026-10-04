"""问数缓存 Redis 仓储。"""

from redis.asyncio import Redis


class CacheRepository:
    """提供独立 namespace 下的缓存基础操作。"""

    namespace = "shopkeeper:cache:"

    def __init__(self, client: Redis | None):
        self.client = client

    def _is_cache_key(self, key: str) -> bool:
        return key.startswith(self.namespace)

    async def get(self, key: str) -> str | None:
        """读取缓存值；未启用、未初始化或非缓存 Key 均视为 miss。"""

        if self.client is None or not self._is_cache_key(key):
            return None
        value = await self.client.get(key)
        return value if isinstance(value, str) else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """写入带 TTL 的缓存值。"""

        if self.client is None or not self._is_cache_key(key):
            return
        await self.client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        """删除缓存值，不触碰 SSE namespace。"""

        if self.client is None or not self._is_cache_key(key):
            return
        await self.client.delete(key)

    async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        """尝试获取短时锁。"""

        if self.client is None or not self._is_cache_key(key):
            return False
        return bool(await self.client.set(key, "1", ex=ttl_seconds, nx=True))
