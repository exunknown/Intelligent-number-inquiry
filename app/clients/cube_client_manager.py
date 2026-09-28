"""Cube HTTP 客户端生命周期管理。"""

from functools import lru_cache

import httpx

from app.conf.app_config import CubeConfig, app_config


class CubeClientManager:
    """管理 Cube 异步 HTTP 客户端的创建和关闭。"""

    def __init__(self, config: CubeConfig):
        self.config = config
        self.client: httpx.AsyncClient | None = None

    def init(self) -> None:
        """创建客户端，不在启动阶段访问 Cube 服务。"""
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url.rstrip("/"),
            timeout=httpx.Timeout(self.config.timeout_seconds),
        )

    async def close(self) -> None:
        """关闭已创建的客户端。"""
        if self.client is not None:
            await self.client.aclose()
            self.client = None


@lru_cache(maxsize=1)
def get_cube_client_manager() -> CubeClientManager:
    """获取进程级 Cube 客户端管理器。"""
    return CubeClientManager(app_config.cube)
