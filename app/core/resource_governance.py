"""单实例问数请求的资源预算与准入控制。"""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Any, Awaitable, Callable, TypeVar

from langchain_core.callbacks import BaseCallbackHandler

from app.conf.app_config import app_config
from app.core.log import logger
from app.core.query_errors import QueryExecutionError

T = TypeVar("T")


class LLMUsageCallbackHandler(BaseCallbackHandler):
    """聚合单次请求内模型响应返回的输入和输出 token。"""

    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()
        self._input_tokens = 0
        self._output_tokens = 0
        self._has_usage = False

    @staticmethod
    def _read_token_pair(value: Any) -> tuple[int, int] | None:
        if not isinstance(value, dict):
            return None
        nested = value.get("token_usage")
        if nested is not None:
            return LLMUsageCallbackHandler._read_token_pair(nested)
        input_tokens = value.get("input_tokens", value.get("prompt_tokens"))
        output_tokens = value.get("output_tokens", value.get("completion_tokens"))
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            return None
        return input_tokens, output_tokens

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """读取 LangChain 标准 usage_metadata，兼容旧 token_usage 结构。"""

        for generations in getattr(response, "generations", ()):
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = self._read_token_pair(getattr(message, "usage_metadata", None))
                if usage is None:
                    usage = self._read_token_pair(
                        getattr(generation, "generation_info", None)
                    )
                if usage is None:
                    usage = self._read_token_pair(getattr(response, "llm_output", None))
                if usage is None:
                    continue
                with self._lock:
                    self._input_tokens += usage[0]
                    self._output_tokens += usage[1]
                    self._has_usage = True
                return

    def totals(self) -> tuple[int | None, int | None]:
        """返回聚合结果；下游未提供 usage 时保留空值。"""

        with self._lock:
            if not self._has_usage:
                return None, None
            return self._input_tokens, self._output_tokens


def _counts_as_dependency_failure(dependency: str | None, error: BaseException) -> bool:
    """只把传输层/超时错误计入熔断，模型结构错误不应触发熔断。"""

    if dependency != "llm":
        return True
    if isinstance(error, TimeoutError):
        return True
    return type(error).__module__.split(".", 1)[0] in {"httpx", "openai"}


class RequestBodyTooLarge(ValueError):
    """请求体超过接口配置的字节上限。"""


class DependencyCircuitBreaker:
    """单实例依赖熔断器，避免连续故障继续占用下游连接。"""

    def __init__(
        self,
        failure_threshold: int = 3,
        open_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if failure_threshold <= 0 or open_seconds <= 0:
            raise ValueError("circuit breaker settings must be positive")
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self.clock = clock
        self._state = "closed"
        self._failure_count = 0
        self._opened_at = 0.0
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    async def before_call(self) -> None:
        async with self._lock:
            if self._state == "closed":
                return
            if self._state == "open":
                if self.clock() - self._opened_at < self.open_seconds:
                    raise QueryExecutionError(
                        "dependency_circuit_open", "下游服务暂时熔断，请稍后重试", True
                    )
                self._state = "half_open"
            if self._probe_in_flight:
                raise QueryExecutionError(
                    "dependency_circuit_open", "下游服务正在恢复，请稍后重试", True
                )
            self._probe_in_flight = True

    async def record_success(self) -> None:
        async with self._lock:
            self._state = "closed"
            self._failure_count = 0
            self._probe_in_flight = False

    async def record_failure(self) -> None:
        async with self._lock:
            self._probe_in_flight = False
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = "open"
                self._opened_at = self.clock()


@lru_cache(maxsize=1)
def get_dependency_breakers() -> dict[str, DependencyCircuitBreaker]:
    """获取应用进程级依赖熔断器，单实例部署内共享状态。"""

    names = (
        "llm",
        "embedding",
        "qdrant",
        "elasticsearch",
        "mysql_meta",
        "mysql_dw",
    )
    return {
        name: DependencyCircuitBreaker(
            failure_threshold=app_config.resource.circuit_failure_threshold,
            open_seconds=app_config.resource.circuit_open_seconds,
        )
        for name in names
    }


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
    max_llm_calls: int = 32
    max_embedding_calls: int = 64
    llm_calls: int = 0
    embedding_calls: int = 0

    @classmethod
    def from_timeout(
        cls,
        timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_llm_calls: int = 32,
        max_embedding_calls: int = 64,
    ) -> "RequestBudget":
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if min(max_llm_calls, max_embedding_calls) <= 0:
            raise ValueError("resource call limits must be positive")
        return cls(
            deadline=clock() + timeout_seconds,
            clock=clock,
            max_llm_calls=max_llm_calls,
            max_embedding_calls=max_embedding_calls,
        )

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline - self.clock())

    def check(self) -> None:
        if self.remaining_seconds() <= 0:
            raise QueryExecutionError(
                "resource_deadline_exceeded", "问数请求已超过时间预算", False
            )

    def timeout_seconds(self, dependency_timeout_seconds: float) -> float:
        """返回不超过请求剩余时间的依赖超时。"""

        if dependency_timeout_seconds <= 0:
            raise ValueError("dependency_timeout_seconds must be positive")
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise QueryExecutionError(
                "resource_deadline_exceeded", "问数请求已超过时间预算", False
            )
        return min(dependency_timeout_seconds, remaining)

    def consume(self, resource: str) -> None:
        if resource == "llm":
            self.llm_calls += 1
            used, allowed = self.llm_calls, self.max_llm_calls
        elif resource == "embedding":
            self.embedding_calls += 1
            used, allowed = self.embedding_calls, self.max_embedding_calls
        else:
            raise ValueError(f"unsupported resource: {resource}")
        if used > allowed:
            raise QueryExecutionError(
                "resource_budget_exceeded", "问数请求资源预算已用尽", False
            )


async def await_with_budget(
    awaitable: Awaitable[T],
    budget: RequestBudget | None,
    resource: str | None = None,
    circuit_breaker: DependencyCircuitBreaker | None = None,
    dependency: str | None = None,
) -> T:
    """等待一个下游调用，并把超时转换为稳定的资源错误。"""

    if circuit_breaker is not None:
        try:
            await circuit_breaker.before_call()
        except QueryExecutionError:
            close = getattr(awaitable, "close", None)
            if close is not None:
                close()
            raise
    try:
        if budget is None:
            result = await awaitable
        else:
            budget.check()
            if resource is not None:
                budget.consume(resource)
            async with asyncio.timeout(budget.remaining_seconds()):
                result = await awaitable
    except asyncio.CancelledError:
        raise
    except QueryExecutionError as error:
        if (
            circuit_breaker is not None
            and _counts_as_dependency_failure(dependency, error)
            and error.code
            not in {
                "resource_deadline_exceeded",
                "resource_budget_exceeded",
                "dependency_circuit_open",
            }
        ):
            await circuit_breaker.record_failure()
        logger.warning(
            "resource_event=budget_rejected resource_class={} dependency={} deadline_ms={} resource={}",
            "dependency" if resource else "request",
            dependency or "unknown",
            round(budget.remaining_seconds() * 1000) if budget else None,
            resource or "request",
        )
        close = getattr(awaitable, "close", None)
        if close is not None:
            close()
        raise
    except TimeoutError:
        if circuit_breaker is not None and _counts_as_dependency_failure(
            dependency, TimeoutError()
        ):
            await circuit_breaker.record_failure()
        logger.warning(
            "resource_event=deadline_exceeded resource_class={} dependency={} deadline_ms={} resource={}",
            "dependency" if resource else "request",
            dependency or "unknown",
            round(budget.remaining_seconds() * 1000) if budget else None,
            resource or "request",
        )
        raise QueryExecutionError(
            "resource_deadline_exceeded", "问数请求已超过时间预算", False
        ) from None
    except Exception:
        if circuit_breaker is not None and _counts_as_dependency_failure(
            dependency, RuntimeError()
        ):
            await circuit_breaker.record_failure()
        raise
    else:
        if circuit_breaker is not None:
            await circuit_breaker.record_success()
        return result


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
                logger.warning(
                    "resource_event=admission_rejected resource_class=request reason=rate_limited user_id={}",
                    user_id,
                )
                raise QueryExecutionError(
                    "rate_limited", "请求过于频繁，请稍后重试", True
                )
            if self._global_in_use >= self.global_limit:
                logger.warning(
                    "resource_event=admission_rejected resource_class=request reason=capacity_exhausted user_id={} concurrency_in_use={}",
                    user_id,
                    self._global_in_use,
                )
                raise QueryExecutionError(
                    "capacity_exhausted", "当前问数容量已满，请稍后重试", True
                )
            if self._user_in_use[user_id] >= self.user_limit:
                logger.warning(
                    "resource_event=admission_rejected resource_class=request reason=user_capacity_exhausted user_id={}",
                    user_id,
                )
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
