"""单实例问数请求的资源预算与准入控制。"""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from app.conf.app_config import app_config
from app.core.query_errors import QueryExecutionError


class RequestBodyTooLarge(ValueError):
    """请求体超过接口配置的字节上限。"""


def validate_content_length(content_length: str | None, max_bytes: int) -> int | None:
    """校验声明的请求体大小，缺少长度时交由 ASGI 接收器累计校验。"""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if content_length is None:
        return None
    try:
        length = int(content_length)
    except (TypeError, ValueError) as exc:
        raise RequestBodyTooLarge("invalid content length") from exc
    if length < 0 or length > max_bytes:
        raise RequestBodyTooLarge("request body is too large")
    return length


class QueryBodyLimitMiddleware:
    """只为问数接口限制请求体字节数，兼容 Content-Length 和分块请求。"""

    def __init__(self, app, max_bytes: int):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != "/api/query":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        try:
            validate_content_length(
                content_length.decode("ascii") if content_length else None,
                self.max_bytes,
            )
        except RequestBodyTooLarge:
            await self._send_rejection(send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestBodyTooLarge("request body is too large")
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self._send_rejection(send)

    @staticmethod
    async def _send_rejection(send) -> None:
        body = '{"detail":"请求体超过大小限制"}'.encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


@dataclass(slots=True)
class RequestBudget:
    """使用单调时钟计算的请求级截止时间。"""

    deadline: float
    clock: Callable[[], float] = time.monotonic

    @classmethod
    def from_timeout(
        cls, timeout_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> "RequestBudget":
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        return cls(deadline=clock() + timeout_seconds, clock=clock)

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - self.clock())

    def check(self) -> None:
        if self.remaining_seconds() <= 0:
            raise QueryExecutionError(
                "resource_deadline_exceeded", "问数请求已超过时间预算", False
            )


class AdmissionLease:
    """一次请求准入占用的资源槽，允许重复释放。"""

    def __init__(self, admission: "ResourceAdmission", user_id: str):
        self._admission = admission
        self._user_id = user_id
        self._released = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._admission._release(self._user_id)


class ResourceAdmission:
    """进程内全局/用户并发和固定窗口速率控制。"""

    def __init__(
        self,
        global_limit: int,
        user_limit: int,
        rate_limit: int,
        rate_window_seconds: float = 60.0,
    ):
        if min(global_limit, user_limit, rate_limit) <= 0:
            raise ValueError("resource limits must be positive")
        if rate_window_seconds <= 0:
            raise ValueError("rate_window_seconds must be positive")
        self.global_limit = global_limit
        self.user_limit = user_limit
        self.rate_limit = rate_limit
        self.rate_window_seconds = rate_window_seconds
        self._global_in_use = 0
        self._user_in_use: dict[str, int] = defaultdict(int)
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    @property
    def in_use(self) -> int:
        return self._global_in_use

    async def acquire(self, user_id: str, clock: Callable[[], float] = time.monotonic):
        if not user_id:
            raise QueryExecutionError("invalid_identity", "用户身份无效", False)
        now = clock()
        async with self._lock:
            request_times = self._requests[user_id]
            cutoff = now - self.rate_window_seconds
            while request_times and request_times[0] <= cutoff:
                request_times.popleft()
            if len(request_times) >= self.rate_limit:
                raise QueryExecutionError(
                    "rate_limited", "请求过于频繁，请稍后重试", True
                )
            if self._global_in_use >= self.global_limit:
                raise QueryExecutionError(
                    "capacity_exhausted", "当前问数容量已满，请稍后重试", True
                )
            if self._user_in_use[user_id] >= self.user_limit:
                raise QueryExecutionError(
                    "user_capacity_exhausted", "当前用户请求数已达上限", True
                )
            request_times.append(now)
            self._global_in_use += 1
            self._user_in_use[user_id] += 1
            return AdmissionLease(self, user_id)

    async def _release(self, user_id: str) -> None:
        async with self._lock:
            self._global_in_use = max(0, self._global_in_use - 1)
            if self._user_in_use[user_id] <= 1:
                self._user_in_use.pop(user_id, None)
            else:
                self._user_in_use[user_id] -= 1


@lru_cache(maxsize=1)
def get_resource_admission() -> ResourceAdmission:
    """获取应用进程级问数准入器。"""

    return ResourceAdmission(
        global_limit=app_config.resource.global_concurrency,
        user_limit=app_config.resource.user_concurrency,
        rate_limit=app_config.resource.rate_limit,
        rate_window_seconds=app_config.resource.rate_window_seconds,
    )
