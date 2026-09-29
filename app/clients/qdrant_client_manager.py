"""
Qdrant 客户端管理器（单例）

统一创建和管理 Qdrant 异步客户端
主要用于保存字段和指标的向量索引，支撑后续问数流程中的语义召回
"""

from functools import lru_cache
from typing import Optional

from qdrant_client import AsyncQdrantClient

from app.conf.app_config import QdrantConfig, app_config


class QdrantClientManager:
    """管理 Qdrant 客户端的初始化与关闭"""

    def __init__(self, qdrant_config: QdrantConfig):
        # 保存配置对象，后面初始化客户端时要从这里读取 host 和 port
        self.qdrant_config = qdrant_config
        # 先把 client 声明出来，真正初始化放到 init() 中进行
        self.client: Optional[AsyncQdrantClient] = None

    def _get_url(self) -> str:
        """拼接 Qdrant 服务地址"""
        return f"http://{self.qdrant_config.host}:{self.qdrant_config.port}"

    def init(self):
        """
        显式初始化 Qdrant 客户端
        这里不在 __init__ 中直接初始化，是为了和项目的生命周期管理保持一致
        """
        self.client = AsyncQdrantClient(
            url=self._get_url(), timeout=self.qdrant_config.timeout_seconds
        )

    async def close(self):
        """关闭 Qdrant 客户端连接"""
        await self.client.close()


# 用 lru_cache 保证全进程只构造一个管理器实例
# 后续项目中的其他模块都通过它来获取同一套 Qdrant 客户端
@lru_cache(maxsize=1)
def get_qdrant_client_manager() -> QdrantClientManager:
    return QdrantClientManager(app_config.qdrant)
