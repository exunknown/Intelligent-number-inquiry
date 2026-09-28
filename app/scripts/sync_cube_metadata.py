"""手动同步 Cube 受治理成员到 Qdrant。"""

import asyncio
import inspect

from app.clients.cube_client_manager import get_cube_client_manager
from app.clients.embedding_client_manager import get_embedding_client_manager
from app.clients.qdrant_client_manager import get_qdrant_client_manager
from app.conf.app_config import app_config
from app.core.log import logger
from app.repositories.cube.cube_repository import CubeRepository
from app.repositories.qdrant.cube_member_qdrant_repository import (
    CubeMemberQdrantRepository,
)
from app.services.cube_metadata_service import CubeMetadataService


async def _close_embedding_client(client: object) -> None:
    """关闭 HuggingFace Embedding 内部的同步与异步 HTTP 客户端。"""

    errors: list[Exception] = []
    for attribute in ("async_client", "client"):
        inner_client = getattr(client, attribute, None)
        close = getattr(inner_client, "aclose", None) or getattr(
            inner_client, "close", None
        )
        if close is not None:
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                errors.append(error)
    if errors:
        raise ExceptionGroup("Embedding clients failed to close", errors)


async def sync() -> None:
    """初始化三类客户端，执行同步，并在 finally 中逐一关闭。"""

    cube_manager = get_cube_client_manager()
    qdrant_manager = get_qdrant_client_manager()
    embedding_manager = get_embedding_client_manager()

    try:
        cube_manager.init()
        qdrant_manager.init()
        embedding_manager.init()
        service = CubeMetadataService(
            cube_repository=CubeRepository(cube_manager.client, app_config.cube),
            cube_member_qdrant_repository=CubeMemberQdrantRepository(
                qdrant_manager.client
            ),
            embedding_client=embedding_manager.client,
            semantic_view=app_config.cube.semantic_view,
        )
        result = await service.sync()
        logger.info(
            "Cube 元数据同步完成 compiler_id={} member_count={} point_count={}",
            result.compiler_id,
            result.member_count,
            result.point_count,
        )
    finally:
        close_tasks = []
        if cube_manager.client is not None:
            close_tasks.append(cube_manager.close())
        if qdrant_manager.client is not None:
            close_tasks.append(qdrant_manager.close())
        if embedding_manager.client is not None:
            close_tasks.append(_close_embedding_client(embedding_manager.client))
        close_results = await asyncio.gather(*close_tasks, return_exceptions=True)
        embedding_manager.client = None
        for result in close_results:
            if isinstance(result, Exception):
                logger.warning(
                    "Cube 元数据同步客户端关闭失败 type={}", type(result).__name__
                )


if __name__ == "__main__":
    asyncio.run(sync())
