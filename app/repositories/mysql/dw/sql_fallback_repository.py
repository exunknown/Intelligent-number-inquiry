"""受限 SQL fallback 查询的专用只读仓储。"""

import asyncio
import json
import math
from time import perf_counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.conf.app_config import SQLSafetyConfig
from app.core.log import logger
from app.core.query_errors import QueryExecutionError
from app.entities.sql_execution import SQLCostEstimate, SQLExecutionResult

_MYSQL_QUERY_TIMEOUT_CODE = 3024
_ROW_ESTIMATE_KEYS = frozenset({"rows_examined_per_scan", "rows_produced_per_join"})


class SQLFallbackRepository:
    """只执行策略引擎生成的最终 SQL，并强制资源预算。"""

    def __init__(self, session: AsyncSession, config: SQLSafetyConfig):
        self.session = session
        self.config = config

    async def explain(self, executable_sql: str) -> SQLCostEstimate:
        """解析 MySQL JSON 执行计划并拒绝超预算查询。"""

        try:
            await self._set_server_timeout()
            async with asyncio.timeout(self.config.max_execution_ms / 1000):
                result = await self.session.execute(
                    text(f"EXPLAIN FORMAT=JSON {executable_sql}")
                )
            estimate = self._parse_explain(result.scalar_one_or_none())
        except TimeoutError:
            await self._invalidate()
            raise self._timeout_error() from None
        except QueryExecutionError:
            raise
        except Exception as exc:
            if self._is_server_timeout(exc):
                await self._invalidate()
                raise self._timeout_error() from None
            self._log_failure("sql_execution_failed")
            raise self._execution_error() from None

        if (
            estimate.estimated_rows > self.config.max_estimated_rows
            or estimate.query_cost > self.config.max_query_cost
        ):
            raise QueryExecutionError(
                "sql_cost_exceeded",
                "查询成本超过安全限制",
                False,
            )
        return estimate

    async def run(self, executable_sql: str) -> SQLExecutionResult:
        """流式读取查询结果并强制行数、字节数与超时预算。"""

        started_at = perf_counter()
        try:
            await self._set_server_timeout()
            async with asyncio.timeout(self.config.max_execution_ms / 1000):
                result = await self.session.stream(text(executable_sql))
                rows, truncated = await self._read_rows(result.mappings())
        except TimeoutError:
            await self._invalidate()
            raise self._timeout_error() from None
        except QueryExecutionError:
            raise
        except Exception as exc:
            if self._is_server_timeout(exc):
                await self._invalidate()
                raise self._timeout_error() from None
            self._log_failure("sql_execution_failed")
            raise self._execution_error() from None

        result_bytes = len(self._serialize_rows(rows))
        return SQLExecutionResult(
            rows=tuple(rows),
            row_count=len(rows),
            result_bytes=result_bytes,
            truncated=truncated,
            duration_ms=max(0, round((perf_counter() - started_at) * 1000)),
        )

    async def _set_server_timeout(self) -> None:
        await self.session.execute(
            text("SET SESSION MAX_EXECUTION_TIME = :max_execution_ms"),
            {"max_execution_ms": self.config.max_execution_ms},
        )

    async def _read_rows(self, result: Any) -> tuple[list[dict[str, Any]], bool]:
        rows: list[dict[str, Any]] = []
        async for partition in result.partitions(100):
            for row in partition:
                if len(rows) >= self.config.max_rows:
                    return rows, True
                candidate = [*rows, dict(row)]
                if len(self._serialize_rows(candidate)) > self.config.max_result_bytes:
                    raise QueryExecutionError(
                        "sql_result_too_large",
                        "查询结果超过安全限制",
                        False,
                    )
                rows = candidate
        return rows, False

    @staticmethod
    def _serialize_rows(rows: Any) -> bytes:
        return json.dumps(
            rows,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def _parse_explain(cls, payload: Any) -> SQLCostEstimate:
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValueError("invalid explain payload")

        row_estimates: list[float] = []
        query_costs: list[float] = []
        cls._collect_plan_numbers(payload, row_estimates, query_costs)
        if not query_costs:
            raise ValueError("missing query cost")
        return SQLCostEstimate(
            estimated_rows=math.ceil(sum(row_estimates)),
            query_cost=max(query_costs),
        )

    @classmethod
    def _collect_plan_numbers(
        cls,
        value: Any,
        row_estimates: list[float],
        query_costs: list[float],
    ) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _ROW_ESTIMATE_KEYS:
                    row_estimates.append(cls._number(child))
                elif key == "query_cost":
                    query_costs.append(cls._number(child))
                else:
                    cls._collect_plan_numbers(child, row_estimates, query_costs)
        elif isinstance(value, list):
            for child in value:
                cls._collect_plan_numbers(child, row_estimates, query_costs)

    @staticmethod
    def _number(value: Any) -> float:
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError("invalid explain number")
        return number

    async def _invalidate(self) -> None:
        try:
            await self.session.invalidate()
        except Exception:
            self._log_failure("sql_connection_invalidation_failed")

    @staticmethod
    def _is_server_timeout(exc: Exception) -> bool:
        current: BaseException | None = exc
        while current is not None:
            if current.args and current.args[0] == _MYSQL_QUERY_TIMEOUT_CODE:
                return True
            current = current.__cause__ or current.__context__
        return False

    @staticmethod
    def _timeout_error() -> QueryExecutionError:
        return QueryExecutionError("sql_timeout", "SQL 查询执行超时", True)

    @staticmethod
    def _execution_error() -> QueryExecutionError:
        return QueryExecutionError("sql_execution_failed", "SQL 查询执行失败", False)

    @staticmethod
    def _log_failure(code: str) -> None:
        logger.error("SQL fallback operation failed code={}", code)
