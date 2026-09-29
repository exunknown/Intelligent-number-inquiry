"""Cube 数据服务访问仓储。"""

import re
import time
from collections.abc import Callable, Collection

import httpx
import jwt

from app.conf.app_config import CubeConfig
from app.core.log import logger
from app.core.query_errors import QueryExecutionError

_DEPARTMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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

    async def load(
        self,
        query: dict,
        user_id: str,
        department_ids: Collection[str],
        policy_version: int,
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
        token_claims: dict | None = None,
        **kwargs: object,
    ) -> dict:
        started_at = time.monotonic()
        try:
            response = await self.client.request(
                method,
                path,
                headers={"Authorization": self._create_token(token_claims)},
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
