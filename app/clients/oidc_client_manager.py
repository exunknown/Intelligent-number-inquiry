"""OIDC HTTP 客户端生命周期管理。"""

from functools import lru_cache

import httpx

from app.conf.app_config import AuthConfig, app_config


class OIDCClientManager:
    """管理获取 JWKS 使用的异步 HTTP 客户端。"""

    def __init__(self, config: AuthConfig):
        self.config = config
        self.client: httpx.AsyncClient | None = None

    def init(self) -> None:
        """创建客户端，启动阶段不主动访问身份服务。"""
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))

    async def close(self) -> None:
        """关闭已创建的客户端。"""
        if self.client is not None:
            await self.client.aclose()
            self.client = None


@lru_cache(maxsize=1)
def get_oidc_client_manager() -> OIDCClientManager:
    """获取进程级 OIDC 客户端管理器。"""
    return OIDCClientManager(app_config.auth)
