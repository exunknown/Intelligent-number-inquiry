"""将 QueryService 的隔离 SSE 执行转换为评测观测。"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Protocol

from app.evaluation.runner import EvaluationCase, EvaluationObservation


class QueryServiceProtocol(Protocol):
    def query(self, query: str, principal, lease=None): ...


class QueryServiceEvaluationExecutor:
    """使用固定评测身份执行样本，不保存结果正文或完整 SQL。"""

    def __init__(self, query_service: QueryServiceProtocol):
        self.query_service = query_service

    async def run_case(self, case: EvaluationCase) -> EvaluationObservation:
        if not case.query or case.identity is None:
            raise ValueError(f"执行样本缺少 query 或 identity: {case.case_id}")

        started_at = perf_counter()
        actual_route: str | None = None
        actual_resources: tuple[str, ...] = ()
        outcome: str | None = None
        rejection_code: str | None = None
        result_valid: bool | None = None
        async for frame in self.query_service.query(
            case.query, principal=case.identity.to_principal()
        ):
            event = _parse_sse_frame(frame)
            event_type = event.get("type")
            if event_type == "route":
                actual_route = _allowed_route(event.get("mode"))
            elif event_type == "metrics":
                actual_resources = _string_items(event.get("data"))
            elif event_type == "result":
                outcome = "success"
                result_valid = event.get("verified") is True
                if actual_route is None:
                    actual_route = _allowed_route(event.get("source"))
            elif event_type == "error":
                outcome = "reject"
                rejection_code = _stable_code(event.get("code"))
                if actual_route is None:
                    actual_route = "reject"

        if outcome is None or actual_route is None:
            raise ValueError(f"评测样本未产生终态事件: {case.case_id}")
        return EvaluationObservation(
            case_id=case.case_id,
            actual_route=actual_route,
            actual_resources=actual_resources,
            outcome=outcome,
            latency_ms=round((perf_counter() - started_at) * 1000, 3),
            rejection_code=rejection_code,
            result_valid=result_valid,
        )


def _parse_sse_frame(frame: str) -> dict:
    if not isinstance(frame, str) or not frame.startswith("data: "):
        raise ValueError("评测执行收到非法 SSE 帧")
    payload = frame.removeprefix("data: ").strip()
    try:
        event = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("评测执行收到非法 JSON 事件") from error
    if not isinstance(event, dict):
        raise ValueError("评测执行事件必须是 JSON 对象")
    return event


def _allowed_route(value: object) -> str:
    if value in {"metric", "sql", "reject"}:
        return value
    raise ValueError("评测执行收到未知路由")


def _stable_code(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 96:
        raise ValueError("评测执行收到非法错误码")
    return value


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError("评测执行收到非法资源列表")
    return tuple(value)
