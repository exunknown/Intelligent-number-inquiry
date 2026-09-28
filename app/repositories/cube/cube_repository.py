"""Cube 数据服务访问仓储。"""

import time
from collections.abc import Callable

import httpx
import jwt

from app.conf.app_config import CubeConfig
from app.core.log import logger
from app.core.query_errors import QueryExecutionError


class CubeRepository:
    """封装 Cube 元数据与查询接口。"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: CubeConfig,
        clock: Callable[[], float] = time.time,
    ):
        self.client = client
        self.config = config
        self.clock = clock

    async def get_metadata(self) -> dict:
        """获取 Cube 元数据。"""
        return await self._request("GET", "/v1/meta")

    async def load(self, query: dict) -> dict:
        """执行 Cube 查询。"""
        return await self._request("POST", "/v1/load", json={"query": query})

    async def _request(self, method: str, path: str, **kwargs: object) -> dict:
        started_at = time.monotonic()
        try:
            response = await self.client.request(
                method,
                path,
                headers={"Authorization": self._create_token()},
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

    def _create_token(self) -> str:
        issued_at = int(self.clock())
        return jwt.encode(
            {"sub": "shopkeeper-agent", "iat": issued_at, "exp": issued_at + 300},
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

    @staticmethod
    def _log(
        method: str,
        path: str,
        status: int | None,
        started_at: float,
        code: str,
    ) -> None:
        logger.info(
            "Cube 请求 method={} path={} status={} duration_ms={} code={}",
            method,
            path,
            status,
            round((time.monotonic() - started_at) * 1000),
            code,
        )
