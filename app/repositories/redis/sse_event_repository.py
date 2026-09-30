"""SSE 短期事件序列 Redis 仓储。"""

import json

from redis.asyncio import Redis

from app.conf.app_config import RedisConfig


class SSEEventRepository:
    """按请求保存有限数量的完整 SSE 帧。"""

    def __init__(self, client: Redis | None, config: RedisConfig):
        self.client = client
        self.config = config

    def _key(self, request_id: str) -> str:
        return f"shopkeeper:sse:{request_id}"

    async def append_frame(self, request_id: str, sequence: int, frame: str) -> None:
        """追加一帧并刷新 TTL；禁用或未初始化时直接跳过。"""

        if self.client is None:
            return
        value = json.dumps(
            {"sequence": sequence, "frame": frame},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        key = self._key(request_id)
        async with self.client.pipeline(transaction=True) as pipeline:
            await (
                pipeline.rpush(key, value)
                .ltrim(key, -self.config.max_events, -1)
                .expire(key, self.config.event_ttl_seconds)
                .execute()
            )

    async def read_frames(
        self, request_id: str, after_sequence: int = 0
    ) -> list[tuple[int, str]]:
        """读取指定序号之后仍在 TTL 内的事件帧。"""

        if self.client is None:
            return []
        values = await self.client.lrange(self._key(request_id), 0, -1)
        frames: list[tuple[int, str]] = []
        for value in values:
            try:
                item = json.loads(value)
                sequence = int(item["sequence"])
                frame = item["frame"]
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
            if sequence > after_sequence and isinstance(frame, str):
                frames.append((sequence, frame))
        return frames
