"""为既有固定元数据资源补建稳定查询 alias。"""

import asyncio

from app.clients.es_client_manager import get_es_client_manager
from app.clients.qdrant_client_manager import get_qdrant_client_manager
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


async def bootstrap() -> None:
    """幂等创建字段、指标和字段值三个 alias。"""
    get_qdrant_client_manager().init()
    get_es_client_manager().init()
    try:
        column_target = await ColumnQdrantRepository(
            get_qdrant_client_manager().client
        ).ensure_alias()
        metric_target = await MetricQdrantRepository(
            get_qdrant_client_manager().client
        ).ensure_alias()
        value_target = await ValueESRepository(
            get_es_client_manager().client
        ).ensure_alias()
        print(
            "metadata aliases ready "
            f"column={column_target} metric={metric_target} value={value_target}"
        )
    finally:
        await get_qdrant_client_manager().close()
        await get_es_client_manager().close()


if __name__ == "__main__":
    asyncio.run(bootstrap())
