"""MinIO 客户端生命周期管理。"""

from functools import lru_cache

from minio import Minio

from app.conf.app_config import MinIOConfig, app_config


class MinIOClientManager:
    """管理进程级 MinIO 同步 SDK 客户端。"""

    def __init__(self, config: MinIOConfig):
        self.config = config
        self.client: Minio | None = None

    def init(self) -> None:
        """初始化 SDK；实际网络探测由生命周期健康检查完成。"""

        if not self.config.enabled:
            self.client = None
            return
        if not self.config.access_key or not self.config.secret_key:
            raise RuntimeError("MinIO credentials are required")
        self.client = Minio(
            self.config.endpoint,
            access_key=self.config.access_key,
            secret_key=self.config.secret_key,
            secure=self.config.secure,
        )

    async def close(self) -> None:
        """释放客户端引用。MinIO SDK 没有长连接池需要关闭。"""

        self.client = None


@lru_cache(maxsize=1)
def get_minio_client_manager() -> MinIOClientManager:
    """获取进程级 MinIO 客户端管理器。"""

    return MinIOClientManager(app_config.minio)
