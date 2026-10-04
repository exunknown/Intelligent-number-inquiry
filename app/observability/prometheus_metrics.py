"""把进程内问数指标转换为 Prometheus Collector。"""

from __future__ import annotations

from collections.abc import Iterable

from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    Metric,
)

from app.core.query_metrics import QueryMetrics, get_query_metrics


def _add_counter(
    metric: CounterMetricFamily,
    values: dict[str, int],
    label_name: str,
) -> None:
    for label, value in sorted(values.items()):
        metric.add_metric([label], value)


def _add_latency_gauges(
    metric: GaugeMetricFamily,
    values: dict[str, dict[str, int | None]],
    label_name: str,
) -> None:
    for label, data in sorted(values.items()):
        for quantile in ("p50", "p95", "p99"):
            value = data.get(f"{quantile}_ms")
            if value is not None:
                metric.add_metric([label, quantile], value)


class QueryMetricsCollector:
    """只导出固定低基数标签的 QueryMetrics 快照。"""

    def __init__(self, metrics: QueryMetrics | None = None) -> None:
        self.metrics = metrics or get_query_metrics()

    def collect(self) -> Iterable[Metric]:
        snapshot = self.metrics.snapshot()

        requests = CounterMetricFamily(
            "shopkeeper_query_requests",
            "问数请求累计数量。",
            labels=["outcome"],
        )
        _add_counter(requests, snapshot["outcomes"], "outcome")
        yield requests

        routes = CounterMetricFamily(
            "shopkeeper_query_routes",
            "问数路由累计数量。",
            labels=["route"],
        )
        _add_counter(routes, snapshot["routes"], "route")
        yield routes

        errors = CounterMetricFamily(
            "shopkeeper_query_errors",
            "问数稳定错误码累计数量。",
            labels=["error_code"],
        )
        _add_counter(errors, snapshot["errors_by_code"], "error_code")
        yield errors

        request_latency = GaugeMetricFamily(
            "shopkeeper_query_request_latency_ms",
            "问数请求延迟分位数（毫秒）。",
            labels=["quantile"],
        )
        for quantile in ("p50", "p95", "p99"):
            value = snapshot["latency_ms"].get(quantile)
            if value is not None:
                request_latency.add_metric([quantile], value)
        yield request_latency

        dependencies = snapshot["dependencies"]
        dependency_calls = CounterMetricFamily(
            "shopkeeper_query_dependency_calls",
            "问数依赖调用累计数量。",
            labels=["dependency"],
        )
        dependency_errors = CounterMetricFamily(
            "shopkeeper_query_dependency_errors",
            "问数依赖失败累计数量。",
            labels=["dependency"],
        )
        dependency_latency = GaugeMetricFamily(
            "shopkeeper_query_dependency_latency_ms",
            "问数依赖延迟分位数（毫秒）。",
            labels=["dependency", "quantile"],
        )
        for dependency, data in sorted(dependencies.items()):
            dependency_calls.add_metric([dependency], data["count"])
            dependency_errors.add_metric([dependency], data["errors"])
            for quantile in ("p50", "p95", "p99"):
                value = data.get(f"{quantile}_ms")
                if value is not None:
                    dependency_latency.add_metric([dependency, quantile], value)
        yield dependency_calls
        yield dependency_errors
        yield dependency_latency

        cache = snapshot["cache"]
        cache_events = CounterMetricFamily(
            "shopkeeper_query_cache_events",
            "问数缓存事件累计数量。",
            labels=["category", "outcome", "reason"],
        )
        cache_latency = GaugeMetricFamily(
            "shopkeeper_query_cache_latency_ms",
            "问数缓存操作延迟分位数（毫秒）。",
            labels=["category", "quantile"],
        )
        for category, data in sorted(cache.items()):
            for outcome, reasons in sorted(data["events"].items()):
                for reason, count in sorted(reasons.items()):
                    cache_events.add_metric([category, outcome, reason], count)
            for quantile in ("p50", "p95", "p99"):
                value = data.get(f"{quantile}_ms")
                if value is not None:
                    cache_latency.add_metric([category, quantile], value)
        yield cache_events
        yield cache_latency

        nodes = snapshot["nodes"]
        node_calls = CounterMetricFamily(
            "shopkeeper_query_node_calls",
            "LangGraph 节点调用累计数量。",
            labels=["node"],
        )
        node_errors = CounterMetricFamily(
            "shopkeeper_query_node_errors",
            "LangGraph 节点失败累计数量。",
            labels=["node"],
        )
        node_latency = GaugeMetricFamily(
            "shopkeeper_query_node_latency_ms",
            "LangGraph 节点延迟分位数（毫秒）。",
            labels=["node", "quantile"],
        )
        for node, data in sorted(nodes.items()):
            node_calls.add_metric([node], data["count"])
            node_errors.add_metric([node], data["errors"])
            for quantile in ("p50", "p95", "p99"):
                value = data.get(f"{quantile}_ms")
                if value is not None:
                    node_latency.add_metric([node, quantile], value)
        yield node_calls
        yield node_errors
        yield node_latency
