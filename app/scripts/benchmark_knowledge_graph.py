"""Benchmark MySQL and Neo4j knowledge graph path expansion."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, Sequence

from app.clients.mysql_client_manager import meta_mysql_client_manager
from app.clients.neo4j_client_manager import get_neo4j_client_manager
from app.conf.app_config import app_config
from app.entities.knowledge_graph import (
    EDGE_TYPES,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    KnowledgeGraphPath,
)
from app.repositories.mysql.meta.knowledge_graph_repository import (
    KnowledgeGraphRepository,
)
from app.repositories.neo4j.knowledge_graph_repository import (
    Neo4jKnowledgeGraphRepository,
)


class GraphRepository(Protocol):
    async def expand_paths(
        self,
        release_version: str,
        seed_node_ids: list[str],
        allowed_edge_types: set[str],
        max_hops: int,
        max_nodes: int,
        max_paths: int,
    ) -> tuple[
        list[KnowledgeGraphNode],
        list[KnowledgeGraphEdge],
        list[KnowledgeGraphPath],
    ]: ...


@dataclass(frozen=True)
class Workload:
    release_version: str
    seed_node_ids: tuple[str, ...]
    allowed_edge_types: frozenset[str]
    max_hops: int
    max_nodes: int
    max_paths: int

    def to_dict(self) -> dict[str, object]:
        return {
            "release_version": self.release_version,
            "seed_node_ids": list(self.seed_node_ids),
            "allowed_edge_types": sorted(self.allowed_edge_types),
            "max_hops": self.max_hops,
            "max_nodes": self.max_nodes,
            "max_paths": self.max_paths,
        }


@dataclass(frozen=True)
class SampleResult:
    latency_ms: float | None
    success: bool
    node_count: int
    edge_count: int
    path_count: int
    signature: str | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class BackendReport:
    backend: str
    warmup_count: int
    samples: tuple[SampleResult, ...]
    duration_seconds: float

    @property
    def success_count(self) -> int:
        return sum(sample.success for sample in self.samples)

    @property
    def error_count(self) -> int:
        return len(self.samples) - self.success_count

    @property
    def errors(self) -> list[dict[str, object]]:
        counter = Counter(
            sample.error_code
            for sample in self.samples
            if not sample.success and sample.error_code
        )
        return [
            {"code": code, "count": count} for code, count in sorted(counter.items())
        ]

    def to_dict(self) -> dict[str, object]:
        result = summarize_samples(self.samples)
        result.update(
            {
                "backend": self.backend,
                "warmup_count": self.warmup_count,
                "duration_seconds": round(self.duration_seconds, 6),
            }
        )
        if self.duration_seconds > 0:
            result["throughput_rps"] = round(
                self.success_count / self.duration_seconds, 6
            )
        else:
            result["throughput_rps"] = None
        return result


def percentile(values: Sequence[float], percentile_rank: float) -> float | None:
    """Return a linearly interpolated percentile, or None for empty input."""

    if not 0 <= percentile_rank <= 100:
        raise ValueError("percentile_rank must be between 0 and 100")
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percentile_rank / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def graph_result_signature(
    nodes: Sequence[KnowledgeGraphNode],
    edges: Sequence[KnowledgeGraphEdge],
    paths: Sequence[KnowledgeGraphPath],
) -> str:
    """Hash only graph topology identifiers, never payload or evidence."""

    payload = {
        "nodes": sorted(node.node_id for node in nodes),
        "edges": sorted(edge.edge_id for edge in edges),
        "paths": sorted(
            (
                {
                    "node_ids": list(path.node_ids),
                    "edge_ids": list(path.edge_ids),
                }
                for path in paths
            ),
            key=lambda item: (tuple(item["node_ids"]), tuple(item["edge_ids"])),
        ),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def summarize_samples(samples: Sequence[SampleResult]) -> dict[str, object]:
    success_samples = [sample for sample in samples if sample.success]
    latencies = [
        sample.latency_ms for sample in success_samples if sample.latency_ms is not None
    ]
    error_counter = Counter(
        sample.error_code
        for sample in samples
        if not sample.success and sample.error_code
    )
    signatures = sorted(
        {sample.signature for sample in success_samples if sample.signature is not None}
    )
    result = {
        "sample_count": len(samples),
        "success_count": len(success_samples),
        "error_count": len(samples) - len(success_samples),
        "error_rate": round((len(samples) - len(success_samples)) / len(samples), 6)
        if samples
        else 0.0,
        "latency_ms": {
            "min": min(latencies) if latencies else None,
            "avg": sum(latencies) / len(latencies) if latencies else None,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "max": max(latencies) if latencies else None,
        },
        "result_shape": {
            "avg_nodes": (
                sum(sample.node_count for sample in success_samples)
                / len(success_samples)
                if success_samples
                else None
            ),
            "avg_edges": (
                sum(sample.edge_count for sample in success_samples)
                / len(success_samples)
                if success_samples
                else None
            ),
            "avg_paths": (
                sum(sample.path_count for sample in success_samples)
                / len(success_samples)
                if success_samples
                else None
            ),
        },
        "errors": [
            {"code": code, "count": count}
            for code, count in sorted(error_counter.items())
        ],
        "signatures": signatures,
    }
    return result


async def _expand_paths(
    repository: GraphRepository | "RepositoryProvider", workload: Workload
) -> tuple[
    list[KnowledgeGraphNode], list[KnowledgeGraphEdge], list[KnowledgeGraphPath]
]:
    acquire = getattr(repository, "acquire", None)
    if acquire is None:
        return await repository.expand_paths(
            workload.release_version,
            list(workload.seed_node_ids),
            set(workload.allowed_edge_types),
            workload.max_hops,
            workload.max_nodes,
            workload.max_paths,
        )
    async with acquire() as acquired_repository:
        return await acquired_repository.expand_paths(
            workload.release_version,
            list(workload.seed_node_ids),
            set(workload.allowed_edge_types),
            workload.max_hops,
            workload.max_nodes,
            workload.max_paths,
        )


async def _measure_one(
    repository: GraphRepository | "RepositoryProvider", workload: Workload
) -> SampleResult:
    started = time.perf_counter()
    try:
        nodes, edges, paths = await _expand_paths(repository, workload)
    except Exception as exc:  # noqa: BLE001 - benchmark records backend failures.
        return SampleResult(
            latency_ms=None,
            success=False,
            node_count=0,
            edge_count=0,
            path_count=0,
            signature=None,
            error_code=type(exc).__name__,
            error_message="backend query failed",
        )
    return SampleResult(
        latency_ms=(time.perf_counter() - started) * 1000,
        success=True,
        node_count=len(nodes),
        edge_count=len(edges),
        path_count=len(paths),
        signature=graph_result_signature(nodes, edges, paths),
    )


async def benchmark_repository(
    repository: GraphRepository | "RepositoryProvider",
    workload: Workload,
    *,
    warmup: int,
    samples: int,
    concurrency: int,
) -> BackendReport:
    """Run a fixed workload with bounded concurrency."""

    _validate_measurement_args(warmup, samples, concurrency)
    for _ in range(warmup):
        await _measure_one(repository, workload)

    semaphore = asyncio.Semaphore(concurrency)

    async def measure_with_limit() -> SampleResult:
        async with semaphore:
            return await _measure_one(repository, workload)

    started = time.perf_counter()
    measured = await asyncio.gather(*(measure_with_limit() for _ in range(samples)))
    return BackendReport(
        backend="unknown",
        warmup_count=warmup,
        samples=tuple(measured),
        duration_seconds=time.perf_counter() - started,
    )


def build_comparison(
    mysql_report: BackendReport, neo4j_report: BackendReport
) -> dict[str, object]:
    mysql = mysql_report.to_dict()
    neo4j = neo4j_report.to_dict()
    mysql_p95 = mysql["latency_ms"]["p95"]
    neo4j_p95 = neo4j["latency_ms"]["p95"]
    p95_delta = None
    p95_ratio = None
    if isinstance(mysql_p95, (int, float)) and isinstance(neo4j_p95, (int, float)):
        p95_delta = round(neo4j_p95 - mysql_p95, 6)
        p95_ratio = round(neo4j_p95 / mysql_p95, 6) if mysql_p95 else None
    return {
        "p95_latency_ms_delta": p95_delta,
        "p95_latency_ms_ratio": p95_ratio,
        "error_rate_delta": round(
            float(neo4j["error_rate"]) - float(mysql["error_rate"]), 6
        ),
        "result_signatures_equal": (
            mysql["success_count"] > 0
            and neo4j["success_count"] > 0
            and mysql["signatures"] == neo4j["signatures"]
        ),
        "decision": "manual_review_required",
    }


def build_report(
    workload: Workload,
    mysql_report: BackendReport,
    neo4j_report: BackendReport,
    generated_at: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "workload": workload.to_dict(),
        "backends": {
            "mysql": mysql_report.to_dict(),
            "neo4j": neo4j_report.to_dict(),
        },
        "comparison": build_comparison(mysql_report, neo4j_report),
    }


def _validate_measurement_args(warmup: int, samples: int, concurrency: int) -> None:
    if warmup < 0:
        raise ValueError("warmup must be non-negative")
    if samples < 1:
        raise ValueError("samples must be positive")
    if not 1 <= concurrency <= 256:
        raise ValueError("concurrency must be between 1 and 256")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="比较 MySQL 与 Neo4j 知识图谱路径查询性能"
    )
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--seed-node", action="append", required=True)
    parser.add_argument("--edge-type", action="append", required=True)
    parser.add_argument("--max-hops", type=int, default=2)
    parser.add_argument("--max-nodes", type=int, default=100)
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--warmup", type=_positive_int, default=5)
    parser.add_argument("--samples", type=_positive_int, default=50)
    parser.add_argument("--concurrency", type=_positive_int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.release_version.strip():
        parser.error("--release-version must not be empty")
    if not args.seed_node or any(not value.strip() for value in args.seed_node):
        parser.error("--seed-node must not be empty")
    if not args.edge_type or any(not value.strip() for value in args.edge_type):
        parser.error("--edge-type must not be empty")
    unknown_edge_types = set(args.edge_type) - EDGE_TYPES
    if unknown_edge_types:
        parser.error(
            "unsupported --edge-type: " + ", ".join(sorted(unknown_edge_types))
        )
    if not 1 <= args.max_hops <= 2:
        parser.error("--max-hops must be between 1 and 2")
    if not 1 <= args.max_nodes <= 500:
        parser.error("--max-nodes must be between 1 and 500")
    if not 1 <= args.max_paths <= 500:
        parser.error("--max-paths must be between 1 and 500")
    if args.concurrency < 1 or args.concurrency > 256:
        parser.error("--concurrency must be between 1 and 256")
    if args.samples < 1:
        parser.error("--samples must be positive")
    return args


class RepositoryProvider(Protocol):
    @asynccontextmanager
    async def acquire(self): ...


class _MySQLRepositoryProvider:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    @asynccontextmanager
    async def acquire(self):
        async with self.session_factory() as session:
            yield KnowledgeGraphRepository(session)


async def run_benchmark(args: argparse.Namespace) -> dict[str, object]:
    """Initialize both backends, run the same workload, and close resources."""

    if not app_config.neo4j.enabled:
        raise RuntimeError("real benchmark requires NEO4J_ENABLED=true")
    workload = Workload(
        release_version=args.release_version,
        seed_node_ids=tuple(args.seed_node),
        allowed_edge_types=frozenset(args.edge_type),
        max_hops=args.max_hops,
        max_nodes=args.max_nodes,
        max_paths=args.max_paths,
    )
    _validate_measurement_args(args.warmup, args.samples, args.concurrency)
    meta_mysql_client_manager.init()
    neo4j_manager = get_neo4j_client_manager()
    neo4j_manager.init()
    try:
        if meta_mysql_client_manager.session_factory is None:
            raise RuntimeError("MySQL client initialization failed")
        if neo4j_manager.client is None:
            raise RuntimeError("Neo4j client initialization failed")
        mysql_provider = _MySQLRepositoryProvider(
            meta_mysql_client_manager.session_factory
        )
        neo4j_repository = Neo4jKnowledgeGraphRepository(
            neo4j_manager.client,
            neo4j_manager.database,
        )
        mysql_report = await benchmark_repository(
            mysql_provider,
            workload,
            warmup=args.warmup,
            samples=args.samples,
            concurrency=args.concurrency,
        )
        neo4j_report = await benchmark_repository(
            neo4j_repository,
            workload,
            warmup=args.warmup,
            samples=args.samples,
            concurrency=args.concurrency,
        )
        mysql_report = BackendReport(
            backend="mysql",
            warmup_count=mysql_report.warmup_count,
            samples=mysql_report.samples,
            duration_seconds=mysql_report.duration_seconds,
        )
        neo4j_report = BackendReport(
            backend="neo4j",
            warmup_count=neo4j_report.warmup_count,
            samples=neo4j_report.samples,
            duration_seconds=neo4j_report.duration_seconds,
        )
        report = build_report(workload, mysql_report, neo4j_report)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return report
    finally:
        await meta_mysql_client_manager.close()
        await neo4j_manager.close()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_benchmark(args))
    if not args.output:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
