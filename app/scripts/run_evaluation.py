"""运行脱敏 JSONL 评测并输出发布门禁报告。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evaluation.runner import (
    EvaluationBaselinePolicy,
    EvaluationCase,
    EvaluationIdentity,
    EvaluationObservation,
    EvaluationRunner,
    EvaluationVersions,
    reject_sensitive_keys,
)


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number} 不是有效 JSON") from error
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{line_number} 必须是 JSON 对象")
        reject_sensitive_keys(record)
        records.append(record)
    return records


def _case(record: dict) -> EvaluationCase:
    identity_record = record.get("identity")
    identity = None
    if identity_record is not None:
        if not isinstance(identity_record, dict):
            raise ValueError("identity 必须是 JSON 对象")
        identity = EvaluationIdentity(
            user_id=identity_record["user_id"],
            username=identity_record.get("username"),
            roles=tuple(identity_record.get("roles", [])),
            policy_version=int(identity_record["policy_version"]),
            allowed_metrics=tuple(identity_record.get("allowed_metrics", [])),
            allowed_tables=tuple(identity_record.get("allowed_tables", [])),
            allowed_columns=tuple(identity_record.get("allowed_columns", [])),
            allowed_department_ids=tuple(
                identity_record.get("allowed_department_ids", [])
            ),
            sql_fallback_allowed=bool(
                identity_record.get("sql_fallback_allowed", False)
            ),
        )
    return EvaluationCase(
        case_id=record["case_id"],
        expected_route=record["expected_route"],
        expected_resources=tuple(record.get("expected_resources", [])),
        expected_outcome=record["expected_outcome"],
        expected_rejection_code=record.get("expected_rejection_code"),
        tags=tuple(record.get("tags", [])),
        query=record.get("query"),
        identity=identity,
    )


def _observation(record: dict) -> EvaluationObservation:
    return EvaluationObservation(
        case_id=record["case_id"],
        actual_route=record["actual_route"],
        actual_resources=tuple(record.get("actual_resources", [])),
        outcome=record["outcome"],
        latency_ms=float(record["latency_ms"]),
        rejection_code=record.get("rejection_code"),
        result_valid=record.get("result_valid"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    for name in (
        "dataset-version",
        "prompt-version",
        "model-version",
        "embedding-version",
        "metadata-release-version",
        "code-version",
    ):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    try:
        cases = [_case(record) for record in _read_jsonl(args.cases)]
        observations = [
            _observation(record) for record in _read_jsonl(args.observations)
        ]
        baseline_report = None
        if args.baseline is not None:
            baseline_report = json.loads(args.baseline.read_text(encoding="utf-8"))
            if not isinstance(baseline_report, dict):
                raise ValueError("baseline 必须是 JSON 对象")
            reject_sensitive_keys(baseline_report)
        versions = EvaluationVersions(
            dataset_version=args.dataset_version,
            prompt_version=args.prompt_version,
            model_version=args.model_version,
            embedding_version=args.embedding_version,
            metadata_release_version=args.metadata_release_version,
            code_version=args.code_version,
        )
        report = EvaluationRunner().run(
            cases,
            observations,
            versions,
            baseline_report=baseline_report,
            baseline_policy=EvaluationBaselinePolicy(),
        )
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except (KeyError, TypeError, ValueError) as error:
        print(f"评测输入无效: {type(error).__name__}")
        return 2
    print(
        f"评测完成 passed={report['gate']['passed']} samples={report['sample_count']}"
    )
    return 0 if report["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
