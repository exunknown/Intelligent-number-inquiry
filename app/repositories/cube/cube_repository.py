"""Cube 数据服务访问仓储。"""

import asyncio
import re
import time
from collections.abc import Callable, Collection

import httpx
import jwt

from app.conf.app_config import CubeConfig
from app.core.log import logger
from app.core.query_errors import QueryExecutionError
from app.core.resource_governance import DependencyCircuitBreaker, RequestBudget

_DEPARTMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class CubeRepository:
    """封装 Cube 元数据与查询接口。"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: CubeConfig,
        clock: Callable[[], float] = time.time,
        max_retries: int = 0,
        retry_backoff_seconds: float = 0,
        circuit_failure_threshold: int = 3,
        circuit_open_seconds: float = 30.0,
        circuit_breaker: DependencyCircuitBreaker | None = None,
    ):
        if max_retries < 0 or retry_backoff_seconds < 0:
            raise ValueError("retry settings cannot be negative")
        self.client = client
        self.config = config
        self.clock = clock
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.circuit_breaker = circuit_breaker or DependencyCircuitBreaker(
            failure_threshold=circuit_failure_threshold,
            open_seconds=circuit_open_seconds,
        )

    async def get_metadata(self, budget: RequestBudget | None = None) -> dict:
        """获取 Cube 元数据。"""
        return await self._request("GET", "/v1/meta", budget=budget)

    async def load(
        self,
        query: dict,
        user_id: str,
        department_ids: Collection[str],
        policy_version: int,
        budget: RequestBudget | None = None,
    ) -> dict:
        """执行 Cube 查询。"""
        if isinstance(department_ids, (str, bytes)):
            raise QueryExecutionError("invalid_data_scope", "数据权限范围无效", False)
        departments = sorted(set(department_ids))
        if not departments:
            raise QueryExecutionError(
                "no_data_scope", "当前用户没有可查询的数据范围", False
            )
        if any(
            not isinstance(department_id, str)
            or _DEPARTMENT_ID_PATTERN.fullmatch(department_id) is None
            for department_id in departments
        ):
            raise QueryExecutionError("invalid_data_scope", "数据权限范围无效", False)
        if not isinstance(user_id, str) or not user_id or len(user_id) > 255:
            raise QueryExecutionError("invalid_identity", "用户身份无效", False)
        if (
            isinstance(policy_version, bool)
            or not isinstance(policy_version, int)
            or policy_version < 0
        ):
            raise QueryExecutionError("invalid_data_scope", "数据权限范围无效", False)

        return await self._request(
            "POST",
            "/v1/load",
            budget=budget,
            token_claims={
                "sub": user_id,
                "department_ids": departments,
                "policy_version": policy_version,
            },
            json={"query": query},
        )

    async def _request(
        self,
        method: str,
        path: str,
        budget: RequestBudget | None = None,
        token_claims: dict | None = None,
        **kwargs: object,
    ) -> dict:
        for attempt in range(self.max_retries + 1):
            try:
                await self.circuit_breaker.before_call()
                result = await self._request_once(
                    method,
                    path,
                    budget=budget,
                    token_claims=token_claims,
                    **kwargs,
                )
                await self.circuit_breaker.record_success()
                return result
            except QueryExecutionError as error:
                if error.code == "dependency_circuit_open":
                    logger.warning(
                        "resource_event=circuit_open resource_class=dependency dependency=cube method={} path={} circuit_state={}",
                        method,
                        path,
                        self.circuit_breaker.state,
                    )
                    raise
                if error.retryable and error.code in {
                    "cube_timeout",
                    "cube_unavailable",
                }:
                    await self.circuit_breaker.record_failure()
                if not error.retryable or attempt >= self.max_retries:
                    raise
                if budget is not None:
                    budget.check()
                logger.warning(
                    "resource_event=dependency_retry resource_class=dependency dependency=cube method={} path={} attempt={} code={} circuit_state={}",
                    method,
                    path,
                    attempt + 2,
                    error.code,
                    self.circuit_breaker.state,
                )
                if self.retry_backoff_seconds > 0:
                    delay = self.retry_backoff_seconds
                    if budget is not None:
                        delay = budget.timeout_seconds(delay)
                    await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    async def _request_once(
        self,
        method: str,
        path: str,
        budget: RequestBudget | None = None,
        token_claims: dict | None = None,
        **kwargs: object,
    ) -> dict:
        started_at = time.monotonic()
        timeout_seconds = self.config.timeout_seconds
        if budget is not None:
            timeout_seconds = budget.timeout_seconds(timeout_seconds)
        try:
            response = await self.client.request(
                method,
                path,
                headers={"Authorization": self._create_token(token_claims)},
                timeout=timeout_seconds,
                **kwargs,
            )
        except httpx.TimeoutException:
            self._log(method, path, None, started_at, "cube_timeout")
            raise QueryExecutionError(
                "cube_timeout", "Cube 服务请求超时", True
            ) from None
        except httpx.RequestError:
            self._log(method, path, None, started_at, "cube_unavailable")
            raise QueryExecutionError(
                "cube_unavailable", "Cube 服务暂不可用", True
            ) from None

        if not response.is_success:
            error = self._map_response_error(response)
            self._log(method, path, response.status_code, started_at, error.code)
            raise error

        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            self._log(
                method, path, response.status_code, started_at, "cube_unavailable"
            )
            raise QueryExecutionError(
                "cube_unavailable", "Cube 服务响应异常", False
            ) from None
        self._log(method, path, response.status_code, started_at, "success")
        return data

    def _create_token(self, claims: dict | None = None) -> str:
        issued_at = int(self.clock())
        payload = {
            "sub": "shopkeeper-agent",
            "iat": issued_at,
            "exp": issued_at + 300,
        }
        if claims is not None:
            payload.update(claims)
        return jwt.encode(
            payload,
            self.config.api_secret,
            algorithm="HS256",
        )

    @staticmethod
    def _map_response_error(response: httpx.Response) -> QueryExecutionError:
        if response.status_code in (401, 403):
            return QueryExecutionError("cube_unauthorized", "Cube 服务认证失败", False)
        if response.status_code == 400:
            response_text = response.text.lower()
            if "unknown member" in response_text or "member not found" in response_text:
                return QueryExecutionError(
                    "metadata_out_of_sync", "Cube 元数据已过期", False
                )
        if response.status_code >= 500:
            return QueryExecutionError("cube_unavailable", "Cube 服务暂不可用", True)
        return QueryExecutionError("cube_unavailable", "Cube 服务请求失败", False)

    def _log(
        self,
        method: str,
        path: str,
        status: int | None,
        started_at: float,
        code: str,
    ) -> None:
        logger.info(
            "resource_class=dependency dependency=cube method={} path={} status={} duration_ms={} circuit_state={} code={}",
            method,
            path,
            status,
            round((time.monotonic() - started_at) * 1000),
            self.circuit_breaker.state,
            code,
        )
