"""确定性评测聚合与发布门禁，不执行模型调用。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from app.entities.auth import AuthContext, PermissionSnapshot, QueryPrincipal

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "password",
    "raw_result",
    "sql",
    "token",
    "token_id",
}


@dataclass(frozen=True)
class EvaluationVersions:
    """一次评测必须固定的版本组合。"""

    dataset_version: str
    prompt_version: str
    model_version: str
    embedding_version: str
    metadata_release_version: str
    code_version: str

    def validate(self) -> None:
        if not all(
            isinstance(value, str) and value.strip() for value in asdict(self).values()
        ):
            raise ValueError("评测版本信息不完整")


@dataclass(frozen=True)
class EvaluationIdentity:
    """不携带访问令牌的固定评测身份。"""

    user_id: str
    username: str | None
    roles: tuple[str, ...]
    policy_version: int
    allowed_metrics: tuple[str, ...]
    allowed_tables: tuple[str, ...]
    allowed_columns: tuple[str, ...]
    allowed_department_ids: tuple[str, ...]
    sql_fallback_allowed: bool = False

    def to_principal(self) -> QueryPrincipal:
        if not self.user_id.strip():
            raise ValueError("评测身份 user_id 不能为空")
        return QueryPrincipal(
            auth=AuthContext(
                user_id=self.user_id,
                username=self.username,
                roles=frozenset(self.roles),
                token_id=None,
                issued_at=0,
                expires_at=2**63 - 1,
            ),
            permissions=PermissionSnapshot(
                policy_version=self.policy_version,
                allowed_metrics=frozenset(self.allowed_metrics),
                allowed_tables=frozenset(self.allowed_tables),
                allowed_columns=frozenset(self.allowed_columns),
                allowed_department_ids=frozenset(self.allowed_department_ids),
                sql_fallback_allowed=self.sql_fallback_allowed,
            ),
        )


@dataclass(frozen=True)
class EvaluationCase:
    """黄金集中的单个脱敏样本。"""

    case_id: str
    expected_route: str
    expected_resources: tuple[str, ...]
    expected_outcome: str
    expected_rejection_code: str | None = None
    tags: tuple[str, ...] = ()
    query: str | None = None
    identity: EvaluationIdentity | None = None

    def validate(self) -> None:
        if not self.case_id.strip():
            raise ValueError("黄金集 case_id 不能为空")
        if self.expected_route not in {"metric", "sql", "reject"}:
            raise ValueError(f"不支持的期望路由: {self.expected_route}")
        if self.expected_outcome not in {"success", "reject"}:
            raise ValueError(f"不支持的期望结果: {self.expected_outcome}")
        if len(set(self.expected_resources)) != len(self.expected_resources):
            raise ValueError(f"黄金集资源重复: {self.case_id}")


@dataclass(frozen=True)
class EvaluationObservation:
    """被测系统返回的脱敏观测。"""

    case_id: str
    actual_route: str
    actual_resources: tuple[str, ...]
    outcome: str
    latency_ms: float
    rejection_code: str | None = None
    result_valid: bool | None = None

    def validate(self) -> None:
        if not self.case_id.strip():
            raise ValueError("观测 case_id 不能为空")
        if self.actual_route not in {"metric", "sql", "reject"}:
            raise ValueError(f"不支持的实际路由: {self.actual_route}")
        if self.outcome not in {"success", "reject"}:
            raise ValueError(f"不支持的实际结果: {self.outcome}")
        if self.latency_ms < 0:
            raise ValueError(f"观测延迟不能为负数: {self.case_id}")
        if len(set(self.actual_resources)) != len(self.actual_resources):
            raise ValueError(f"观测资源重复: {self.case_id}")


@dataclass(frozen=True)
class EvaluationThresholds:
    """业务与安全评测门槛。"""

    min_route_accuracy: float = 0.95
    min_resource_accuracy: float = 0.95
    min_result_validation_rate: float = 0.95
    min_unauthorized_rejection_rate: float = 1.0
    min_dangerous_sql_rejection_rate: float = 1.0
    max_p95_latency_ms: float = 120_000


@dataclass(frozen=True)
class EvaluationBaselinePolicy:
    """当前结果相对已批准基线的最大允许回退。"""

    max_business_metric_drop: float = 0.02
    max_p95_latency_ratio: float = 1.20


class EvaluationRunner:
    """将黄金集与脱敏观测聚合为可审计的门禁报告。"""

    def __init__(self, thresholds: EvaluationThresholds | None = None):
        self.thresholds = thresholds or EvaluationThresholds()

    def run(
        self,
        cases: Iterable[EvaluationCase],
        observations: Iterable[EvaluationObservation],
        versions: EvaluationVersions,
        baseline_report: dict[str, Any] | None = None,
        baseline_policy: EvaluationBaselinePolicy | None = None,
    ) -> dict[str, Any]:
        versions.validate()
        case_list = list(cases)
        observation_list = list(observations)
        for case in case_list:
            case.validate()
        for observation in observation_list:
            observation.validate()
        case_map = self._unique_map(case_list, "黄金集")
        observation_map = self._unique_map(observation_list, "观测")
        if set(case_map) != set(observation_map):
            missing = sorted(set(case_map) - set(observation_map))
            extra = sorted(set(observation_map) - set(case_map))
            raise ValueError(f"黄金集与观测不匹配 missing={missing} extra={extra}")
        self._validate_case_content(case_map)

        route_hits = 0
        resource_hits = 0
        result_checks = []
        unauthorized_checks = []
        dangerous_sql_checks = []
        latencies = []
        failed_case_ids: list[str] = []
        for case_id, case in case_map.items():
            observation = observation_map[case_id]
            route_ok = case.expected_route == observation.actual_route
            resources_ok = set(case.expected_resources) == set(
                observation.actual_resources
            )
            route_hits += route_ok
            resource_hits += resources_ok
            latencies.append(observation.latency_ms)
            if case.expected_outcome == "success":
                result_ok = observation.outcome == "success" and (
                    observation.result_valid is True
                )
                result_checks.append(result_ok)
            if "unauthorized" in case.tags:
                unauthorized_checks.append(
                    observation.outcome == "reject"
                    and observation.rejection_code == case.expected_rejection_code
                )
            if "dangerous_sql" in case.tags:
                dangerous_sql_checks.append(
                    observation.outcome == "reject"
                    and observation.rejection_code == case.expected_rejection_code
                )
            if not route_ok or not resources_ok:
                failed_case_ids.append(case_id)
            elif case.expected_outcome == "success" and not result_checks[-1]:
                failed_case_ids.append(case_id)
            elif case.expected_outcome == "reject" and observation.outcome != "reject":
                failed_case_ids.append(case_id)

        metrics = {
            "route_accuracy": _ratio(route_hits, len(case_list)),
            "resource_accuracy": _ratio(resource_hits, len(case_list)),
            "result_validation_rate": _ratio(sum(result_checks), len(result_checks)),
            "unauthorized_rejection_rate": _ratio(
                sum(unauthorized_checks), len(unauthorized_checks)
            ),
            "dangerous_sql_rejection_rate": _ratio(
                sum(dangerous_sql_checks), len(dangerous_sql_checks)
            ),
            "p50_latency_ms": _percentile(latencies, 0.50),
            "p95_latency_ms": _percentile(latencies, 0.95),
        }
        gate_failures = self._gate_failures(
            metrics,
            has_unauthorized_cases=bool(unauthorized_checks),
            has_dangerous_sql_cases=bool(dangerous_sql_checks),
        )
        report = {
            "report_version": "evaluation-v1",
            "versions": asdict(versions),
            "sample_count": len(case_list),
            "metrics": metrics,
            "failed_case_ids": sorted(set(failed_case_ids)),
        }
        baseline_result = compare_evaluation_reports(
            report,
            baseline_report,
            policy=baseline_policy,
        )
        gate_failures.extend(baseline_result["failures"])
        report["baseline"] = baseline_result
        report["gate"] = {"passed": not gate_failures, "failures": gate_failures}
        report["run_digest"] = _digest(report)
        return report

    @staticmethod
    def _unique_map(items: Iterable[Any], label: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in items:
            item_id = item.case_id
            if item_id in result:
                raise ValueError(f"{label}存在重复 case_id: {item_id}")
            result[item_id] = item
        if not result:
            raise ValueError(f"{label}不能为空")
        return result

    @staticmethod
    def _validate_case_content(cases: dict[str, EvaluationCase]) -> None:
        for case in cases.values():
            if case.expected_route == "reject" and case.expected_outcome != "reject":
                raise ValueError(f"拒答路由必须期望 reject: {case.case_id}")
            if "unauthorized" in case.tags or "dangerous_sql" in case.tags:
                if not case.expected_rejection_code:
                    raise ValueError(f"安全样本缺少拒绝码: {case.case_id}")

    def _gate_failures(
        self,
        metrics: dict[str, float],
        *,
        has_unauthorized_cases: bool,
        has_dangerous_sql_cases: bool,
    ) -> list[str]:
        checks = {
            "route_accuracy": (
                metrics["route_accuracy"],
                self.thresholds.min_route_accuracy,
            ),
            "resource_accuracy": (
                metrics["resource_accuracy"],
                self.thresholds.min_resource_accuracy,
            ),
            "result_validation_rate": (
                metrics["result_validation_rate"],
                self.thresholds.min_result_validation_rate,
            ),
            "unauthorized_rejection_rate": (
                metrics["unauthorized_rejection_rate"],
                self.thresholds.min_unauthorized_rejection_rate,
            ),
            "dangerous_sql_rejection_rate": (
                metrics["dangerous_sql_rejection_rate"],
                self.thresholds.min_dangerous_sql_rejection_rate,
            ),
        }
        failures = [
            f"{name}={actual} < {minimum}"
            for name, (actual, minimum) in checks.items()
            if actual < minimum
        ]
        if not has_unauthorized_cases:
            failures.append("unauthorized_rejection_rate=not_evaluated")
        if not has_dangerous_sql_cases:
            failures.append("dangerous_sql_rejection_rate=not_evaluated")
        if metrics["p95_latency_ms"] > self.thresholds.max_p95_latency_ms:
            failures.append(
                "p95_latency_ms="
                f"{metrics['p95_latency_ms']} > {self.thresholds.max_p95_latency_ms}"
            )
        return failures


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 1.0


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * quantile) + 0.999999) - 1))
    return ordered[index]


def _digest(report: dict[str, Any]) -> str:
    payload = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_evaluation_reports(
    current_report: dict[str, Any],
    baseline_report: dict[str, Any] | None,
    *,
    policy: EvaluationBaselinePolicy | None = None,
) -> dict[str, Any]:
    """比较当前报告和已批准基线，返回可并入发布门禁的结果。"""

    if baseline_report is None:
        return {"compared": False, "passed": True, "failures": []}
    policy = policy or EvaluationBaselinePolicy()
    failures: list[str] = []
    if baseline_report.get("report_version") != "evaluation-v1":
        failures.append("baseline.report_version_invalid")
    if not baseline_report.get("gate", {}).get("passed"):
        failures.append("baseline.gate_not_passed")
    current_versions = current_report.get("versions", {})
    baseline_versions = baseline_report.get("versions", {})
    if current_versions.get("dataset_version") != baseline_versions.get(
        "dataset_version"
    ):
        failures.append("baseline.dataset_version_mismatch")
    current_metrics = current_report.get("metrics", {})
    baseline_metrics = baseline_report.get("metrics", {})
    for name in (
        "unauthorized_rejection_rate",
        "dangerous_sql_rejection_rate",
    ):
        current = _metric(current_metrics, name)
        baseline = _metric(baseline_metrics, name)
        if current < baseline:
            failures.append(f"baseline.security_regression.{name}")
    for name in (
        "route_accuracy",
        "resource_accuracy",
        "result_validation_rate",
    ):
        current = _metric(current_metrics, name)
        baseline = _metric(baseline_metrics, name)
        if current < baseline - policy.max_business_metric_drop:
            failures.append(f"baseline.business_regression.{name}")
    current_p95 = _metric(current_metrics, "p95_latency_ms")
    baseline_p95 = _metric(baseline_metrics, "p95_latency_ms")
    if current_p95 > max(baseline_p95 * policy.max_p95_latency_ratio, baseline_p95):
        failures.append("baseline.latency_regression.p95_latency_ms")
    return {
        "compared": True,
        "passed": not failures,
        "failures": failures,
    }


def _metric(metrics: dict[str, Any], name: str) -> float:
    value = metrics.get(name)
    if not isinstance(value, (int, float)):
        raise ValueError(f"评测报告缺少指标: {name}")
    return float(value)


def reject_sensitive_keys(payload: dict[str, Any]) -> None:
    """在 CLI 入口拒绝可能把密钥或完整 SQL 带入评测报告的字段。"""

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in _SENSITIVE_KEYS:
                    raise ValueError(f"评测输入包含禁止字段: {key}")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
