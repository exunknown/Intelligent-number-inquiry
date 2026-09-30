"""Prometheus 指标采集接口。"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from starlette.responses import Response

from app.conf.app_config import app_config
from app.observability.prometheus_metrics import QueryMetricsCollector


async def metrics_handler(request: Request) -> Response:
    """返回受独立采集令牌保护的 Prometheus 指标。"""

    if not app_config.metrics.enabled:
        raise HTTPException(status_code=404, detail="metrics_disabled")

    expected_token = app_config.metrics.token.strip()
    if not expected_token:
        raise HTTPException(status_code=503, detail="metrics_not_ready")

    authorization = request.headers.get("authorization", "")
    scheme, _, supplied_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied_token.strip(), expected_token
    ):
        raise HTTPException(
            status_code=401,
            detail="invalid_metrics_credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    registry = CollectorRegistry(auto_describe=False)
    registry.register(QueryMetricsCollector())
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
