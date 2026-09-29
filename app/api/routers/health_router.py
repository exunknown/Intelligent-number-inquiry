"""提供给网关和容器编排使用的存活、就绪检查。"""

from fastapi import APIRouter, HTTPException

from app.core.log import logger
from app.scripts.check_metadata_release import verify_active_release

health_router = APIRouter(tags=["health"])


@health_router.get("/health/live")
async def live_handler() -> dict[str, str]:
    """进程可响应即视为存活，不访问外部依赖。"""

    return {"status": "ok"}


@health_router.get("/health/ready")
async def ready_handler() -> dict[str, str | int | None]:
    """只有活动元数据和检索资源一致时才报告就绪。"""

    try:
        result = await verify_active_release()
    except Exception as error:
        logger.warning(
            "应用就绪检查失败 error_type={}",
            type(error).__name__,
        )
        raise HTTPException(status_code=503, detail="service_not_ready") from error
    return {
        "status": "ready",
        "metadata_release_version": result["release_version"],
        "alias_count": result["alias_count"],
    }
