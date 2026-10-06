"""Neo4j 客户端管理器。

Neo4j driver 是应用级异步资源，由 FastAPI lifespan 统一初始化和关闭。
"""

from functools import lru_cache

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.conf.app_config import Neo4jConfig, app_config


class Neo4jClientManager:
    """管理 Neo4j 异步 driver 的生命周期。"""

    def __init__(self, config: Neo4jConfig):
        self.config = config
        self.client: AsyncDriver | None = None
        self.database = config.database

    def init(self) -> None:
        """创建可复用的异步 driver。"""
        if self.client is not None:
            return
        self.client = AsyncGraphDatabase.driver(
            self.config.uri,
            auth=(self.config.user, self.config.password),
            connection_timeout=self.config.timeout_seconds,
        )

    async def close(self) -> None:
        """释放 Neo4j driver 及其连接池。"""
        if self.client is None:
            return
        client = self.client
        self.client = None
        await client.close()


@lru_cache(maxsize=1)
def get_neo4j_client_manager() -> Neo4jClientManager:
    """返回进程级 Neo4j client manager。"""
    return Neo4jClientManager(app_config.neo4j)
