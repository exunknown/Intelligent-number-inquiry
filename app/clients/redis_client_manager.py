"""Redis 异步客户端生命周期管理。"""

from functools import lru_cache

from redis.asyncio import Redis

from app.conf.app_config import RedisConfig, app_config


class RedisClientManager:
    """管理进程级 Redis 客户端。"""

    def __init__(self, config: RedisConfig):
        self.config = config
        self.client: Redis | None = None

    def init(self) -> None:
        """初始化连接池，不在启动阶段执行网络访问。"""

        if not self.config.enabled:
            self.client = None
            return
        self.client = Redis(
            host=self.config.host,
            port=self.config.port,
            db=self.config.db,
            password=self.config.password or None,
            decode_responses=True,
            socket_timeout=self.config.socket_timeout_seconds,
            socket_connect_timeout=self.config.socket_timeout_seconds,
            health_check_interval=30,
        )

    async def close(self) -> None:
        """关闭 Redis 连接池。"""

        if self.client is not None:
            await self.client.aclose()
        self.client = None


@lru_cache(maxsize=1)
def get_redis_client_manager() -> RedisClientManager:
    """获取进程级 Redis 客户端管理器。"""

    return RedisClientManager(app_config.redis)
