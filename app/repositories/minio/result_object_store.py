"""MinIO 查询结果对象存储适配器。"""

import asyncio
import math
from io import BytesIO
from typing import Iterator

from minio import Minio
from minio.commonconfig import Filter
from minio.error import S3Error
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

from app.conf.app_config import MinIOConfig


class ResultObjectStore:
    """用同步 MinIO SDK 做线程池隔离，避免阻塞异步事件循环。"""

    def __init__(self, client: Minio | None, config: MinIOConfig):
        self.client = client
        self.config = config

    async def ensure_bucket(self) -> None:
        if self.client is None:
            return
        exists = await asyncio.to_thread(self.client.bucket_exists, self.config.bucket)
        if not exists:
            await asyncio.to_thread(self.client.make_bucket, self.config.bucket)
        if self.config.configure_lifecycle and hasattr(
            self.client, "set_bucket_lifecycle"
        ):
            lifecycle = LifecycleConfig(
                [
                    Rule(
                        "Enabled",
                        rule_filter=Filter(prefix="query-results/"),
                        rule_id="query-result-retention",
                        expiration=Expiration(
                            days=max(
                                1, math.ceil(self.config.export_ttl_seconds / 86400)
                            )
                        ),
                    )
                ]
            )
            await asyncio.to_thread(
                self.client.set_bucket_lifecycle, self.config.bucket, lifecycle
            )

    async def put_json(self, object_key: str, payload: bytes) -> None:
        """上传 JSON 对象，超过配置上限时拒绝。"""

        if self.client is None:
            raise RuntimeError("MinIO object store is not initialized")
        if len(payload) > self.config.max_object_bytes:
            raise ValueError("result export exceeds object storage limit")
        await self.ensure_bucket()
        await asyncio.to_thread(
            self.client.put_object,
            self.config.bucket,
            object_key,
            BytesIO(payload),
            len(payload),
            "application/json; charset=utf-8",
        )

    async def delete(self, object_key: str) -> None:
        if self.client is not None:
            await asyncio.to_thread(
                self.client.remove_object, self.config.bucket, object_key
            )

    async def exists(self, object_key: str) -> bool:
        """检查对象是否仍存在。"""

        if self.client is None:
            return False
        try:
            await asyncio.to_thread(
                self.client.stat_object, self.config.bucket, object_key
            )
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject", "NotFound"}:
                return False
            raise
        return True

    def iter_object(self, object_key: str) -> Iterator[bytes]:
        """以同步迭代器供 Starlette 线程池流式读取。"""

        if self.client is None:
            raise RuntimeError("MinIO object store is not initialized")
        response = self.client.get_object(self.config.bucket, object_key)
        try:
            while chunk := response.read(64 * 1024):
                yield chunk
        finally:
            response.close()
            response.release_conn()
