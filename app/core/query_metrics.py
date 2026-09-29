"""进程内问数指标聚合。

指标只保留低基数标签和有限长度的延迟样本，不持久化问题文本、SQL 或令牌。
"""

from __future__ import annotations

import threading
from collections import Counter, deque
from functools import lru_cache
from statistics import quantiles
from typing import Deque

_OUTCOMES = {"success", "error", "cancelled", "aborted"}
_ROUTES = {"metric", "sql"}
_DEPENDENCIES = {
    "llm",
    "embedding",
    "qdrant",
    "elasticsearch",
    "mysql_meta",
    "mysql_dw",
    "cube",
    "sql_fallback",
}
_NODE_NAMES = {
    "抽取关键词",
    "召回字段信息",
    "召回指标信息",
    "召回字段取值",
    "召回 Cube 成员",
    "合并召回信息",
    "过滤指标信息",
    "过滤表信息",
    "添加额外上下文",
    "生成 Metric Query",
    "校验 Metric Query",
    "评估Schema规模",
    "Schema Selector",
    "应用Schema筛选",
    "生成SQL",
    "校验SQL",
    "SQL 安全检查",
    "校正SQL",
    "评估SQL成本",
    "执行SQL",
    "执行指标查询",
}
_ERROR_CODES = {
    "capacity_exhausted",
    "cube_unauthorized",
    "cube_timeout",
    "cube_unavailable",
    "dependency_circuit_open",
    "forbidden_resource",
    "internal_error",
    "invalid_data_scope",
    "invalid_identity",
    "invalid_model_output",
    "metadata_out_of_sync",
    "no_data_scope",
    "rate_limited",
    "resource_budget_exceeded",
    "resource_deadline_exceeded",
    "sql_execution_failed",
    "sql_security_not_ready",
    "sql_timeout",
    "unknown_member",
    "user_capacity_exhausted",
}


def _label(value: str | None, allowed: set[str]) -> str:
    return value if value in allowed else "other"


def _percentile(values: list[float], quantile_value: float) -> int | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0])
    return round(
        quantiles(values, n=100, method="inclusive")[
            max(0, min(99, round(quantile_value * 100) - 1))
        ]
    )


class QueryMetrics:
    """线程安全的进程内问数指标聚合器。"""

    def __init__(self, sample_limit: int = 2048):
        if sample_limit <= 0:
            raise ValueError("sample_limit must be positive")
        self._lock = threading.Lock()
        self._latencies: Deque[float] = deque(maxlen=sample_limit)
        self._requests_total = 0
        self._successes_total = 0
        self._errors_total = 0
        self._cancelled_total = 0
        self._outcomes: Counter[str] = Counter()
        self._routes: Counter[str] = Counter()
        self._errors_by_code: Counter[str] = Counter()
        self._node_counts: Counter[str] = Counter()
        self._node_errors: Counter[str] = Counter()
        self._node_latencies: dict[str, Deque[float]] = {}
        self._dependency_counts: Counter[str] = Counter()
        self._dependency_errors: Counter[str] = Counter()
        self._dependency_error_codes: dict[str, Counter[str]] = {}
        self._dependency_latencies: dict[str, Deque[float]] = {}

    def record_node(self, node: str | None, duration_ms: float, outcome: str) -> None:
        """记录固定图步骤的耗时，不保存原始步骤文本。"""

        with self._lock:
            normalized_node = _label(node, _NODE_NAMES)
            self._node_counts[normalized_node] += 1
            self._node_latencies.setdefault(
                normalized_node, deque(maxlen=self._latencies.maxlen)
            ).append(max(0.0, float(duration_ms)))
            if _label(outcome, _OUTCOMES) in {"error", "cancelled", "aborted", "other"}:
                self._node_errors[normalized_node] += 1

    def record_dependency(
        self,
        dependency: str | None,
        duration_ms: float,
        outcome: str,
        error_code: str | None = None,
    ) -> None:
        """记录依赖调用耗时和稳定错误码，不保存 URL、参数或异常原文。"""

        with self._lock:
            normalized_dependency = _label(dependency, _DEPENDENCIES)
            normalized_outcome = _label(outcome, _OUTCOMES)
            self._dependency_counts[normalized_dependency] += 1
            self._dependency_latencies.setdefault(
                normalized_dependency, deque(maxlen=self._latencies.maxlen)
            ).append(max(0.0, float(duration_ms)))
            if normalized_outcome != "success":
                self._dependency_errors[normalized_dependency] += 1
            if error_code is not None:
                self._dependency_error_codes.setdefault(
                    normalized_dependency, Counter()
                )[_label(error_code, _ERROR_CODES)] += 1

    def record_request(
        self,
        duration_ms: float,
        outcome: str,
        route: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """记录一次请求，不接收或保存原始问题、SQL 和结果正文。"""

        with self._lock:
            normalized_outcome = _label(outcome, _OUTCOMES)
            normalized_route = _label(route, _ROUTES)
            self._requests_total += 1
            self._outcomes[normalized_outcome] += 1
            self._routes[normalized_route] += 1
            self._latencies.append(max(0.0, float(duration_ms)))
            if normalized_outcome == "success":
                self._successes_total += 1
            elif normalized_outcome == "cancelled":
                self._cancelled_total += 1
            elif normalized_outcome in {"error", "other"}:
                self._errors_total += 1
            if error_code is not None:
                self._errors_by_code[_label(error_code, _ERROR_CODES)] += 1

    def snapshot(self) -> dict:
        """返回不含敏感字段的指标快照。"""

        with self._lock:
            latencies = list(self._latencies)
            nodes = {
                node: {
                    "count": self._node_counts[node],
                    "errors": self._node_errors[node],
                    "p50_ms": _percentile(list(self._node_latencies[node]), 0.50),
                    "p95_ms": _percentile(list(self._node_latencies[node]), 0.95),
                    "p99_ms": _percentile(list(self._node_latencies[node]), 0.99),
                }
                for node in self._node_counts
            }
            dependencies = {
                dependency: {
                    "count": self._dependency_counts[dependency],
                    "errors": self._dependency_errors[dependency],
                    "p50_ms": _percentile(
                        list(self._dependency_latencies[dependency]), 0.50
                    ),
                    "p95_ms": _percentile(
                        list(self._dependency_latencies[dependency]), 0.95
                    ),
                    "p99_ms": _percentile(
                        list(self._dependency_latencies[dependency]), 0.99
                    ),
                    "errors_by_code": dict(
                        self._dependency_error_codes.get(dependency, {})
                    ),
                }
                for dependency in self._dependency_counts
            }
            return {
                "requests_total": self._requests_total,
                "successes_total": self._successes_total,
                "errors_total": self._errors_total,
                "cancelled_total": self._cancelled_total,
                "outcomes": dict(self._outcomes),
                "routes": dict(self._routes),
                "errors_by_code": dict(self._errors_by_code),
                "nodes": nodes,
                "dependencies": dependencies,
                "latency_ms": {
                    "p50": _percentile(latencies, 0.50),
                    "p95": _percentile(latencies, 0.95),
                    "p99": _percentile(latencies, 0.99),
                },
            }


@lru_cache(maxsize=1)
def get_query_metrics() -> QueryMetrics:
    """返回应用级指标聚合器。"""

    return QueryMetrics()
