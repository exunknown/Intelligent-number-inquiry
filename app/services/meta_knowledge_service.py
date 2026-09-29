"""
元数据知识构建服务

负责组织元数据知识库构建的核心业务流程，位于脚本入口和仓储层之间
一方面接收配置文件，另一方面协调元数据库和数仓查询仓储

当前这条主线已经覆盖表字段入库 字段向量索引 字段取值全文索引
以及指标入库和指标向量索引构建逻辑
"""

import asyncio
import uuid
from dataclasses import asdict
from pathlib import Path

from langchain_huggingface import HuggingFaceEndpointEmbeddings
from omegaconf import OmegaConf

from app.conf.meta_config import MetaConfig
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository

_POINT_ID_NAMESPACE = uuid.UUID("b2a84750-45e7-5e50-8887-c5e81322a4f5")


def _stable_point_id(
    entity_type: str, entity_id: str, entry_type: str, text: str
) -> str:
    identity = f"{entity_type}:{entity_id}:{entry_type}:{text}"
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, identity))


class MetaKnowledgeService:
    """负责串联元数据知识库构建流程的应用服务"""

    def __init__(
        self,
        meta_mysql_repository: MetaMySQLRepository,
        dw_mysql_repository: DWMySQLRepository,
        column_qdrant_repository: ColumnQdrantRepository,
        embedding_client: HuggingFaceEndpointEmbeddings,
        value_es_repository: ValueESRepository,
        metric_qdrant_repository: MetricQdrantRepository,
    ):
        # meta repository 负责结构化元数据的落库
        self.meta_mysql_repository: MetaMySQLRepository = meta_mysql_repository
        # dw repository 负责到教学数仓中读取真实表结构和示例值
        self.dw_mysql_repository: DWMySQLRepository = dw_mysql_repository
        # 字段向量集合的创建和写入统一交给 Qdrant Repository
        self.column_qdrant_repository: ColumnQdrantRepository = column_qdrant_repository
        # 向量化动作放在 Service 层
        self.embedding_client: HuggingFaceEndpointEmbeddings = embedding_client
        # 字段值全文索引的写入统一交给 ES Repository
        self.value_es_repository: ValueESRepository = value_es_repository
        # 指标向量集合和字段向量集合分开管理，便于后续按对象类型独立召回
        self.metric_qdrant_repository: MetricQdrantRepository = metric_qdrant_repository
        self._build_lock = asyncio.Lock()

    async def _commit_staged_indexes(self, staged_indexes):
        """依次切换 staging alias，部分成功时按相反顺序恢复旧 alias。"""
        committed = []
        attempted = []
        try:
            for label, repository, current, previous in staged_indexes:
                attempted.append((label, repository, current, previous))
                await repository.swap_alias(current, previous)
                committed.append((label, repository, current, previous))
        except Exception as error:
            for label, repository, current, previous in reversed(attempted):
                try:
                    if (label, repository, current, previous) not in committed:
                        get_alias_target = getattr(repository, "get_alias_target", None)
                        if get_alias_target is None:
                            continue
                        if await get_alias_target() != current:
                            continue
                    await repository.swap_alias(previous, current)
                except Exception as rollback_error:
                    logger.error(
                        "元数据 alias 回滚失败 label={} error_type={}",
                        label,
                        type(rollback_error).__name__,
                    )
            raise error

    async def _cleanup_staging_resources(self, staging_resources) -> None:
        """清理尚未切换的 staging 物理资源，失败只记录类型。"""
        for repository, resource in staging_resources:
            try:
                cleanup = getattr(repository, "delete_collection", None)
                if cleanup is None:
                    cleanup = getattr(repository, "delete_index")
                await cleanup(resource)
            except Exception as cleanup_error:
                logger.warning(
                    "元数据 staging 清理失败 resource={} error_type={}",
                    resource,
                    type(cleanup_error).__name__,
                )

    async def _save_tables_to_meta_db(
        self, meta_config: MetaConfig
    ) -> list[ColumnInfo]:
        """把配置里的表字段信息补齐后写入 Meta MySQL"""
        table_infos: list[TableInfo] = []
        column_infos: list[ColumnInfo] = []

        for table in meta_config.tables:
            # 先把配置里的表定义整理成业务实体，后面统一交给 Meta Repository 落库
            table_info = TableInfo(
                id=table.name,
                name=table.name,
                role=table.role,
                description=table.description,
            )
            table_infos.append(table_info)

            # 字段类型属于数仓里的真实信息（字段类型），所以这里仍然要回到 DW 查询
            column_types = await self.dw_mysql_repository.get_column_types(table.name)

            for column in table.columns:
                # 这里只拿少量示例值，并且为es（全文检索）提供数据基础
                column_values = await self.dw_mysql_repository.get_column_values(
                    table.name, column.name
                )
                # 字段 id 使用 table.column 形式，后续在向量索引和全文索引里都会复用
                column_info = ColumnInfo(
                    id=f"{table.name}.{column.name}",
                    name=column.name,
                    type=column_types[column.name],
                    role=column.role,
                    examples=column_values,
                    description=column.description,
                    alias=column.alias,
                    table_id=table.name,
                )
                column_infos.append(column_info)
        # 入库
        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_table_infos(table_infos)
            await self.meta_mysql_repository.save_column_infos(column_infos)

        return column_infos

    async def _save_column_info_to_qdrant(
        self,
        column_infos: list[ColumnInfo],
        target_collection: str | None = None,
    ):
        """把字段元数据继续推进成可语义检索的 Qdrant 向量点"""
        if target_collection is None:
            await self.column_qdrant_repository.ensure_collection()
        else:
            await self.column_qdrant_repository.ensure_collection(
                collection_name=target_collection
            )

        points: list[dict] = []
        for column_info in column_infos:
            # 一个字段不会只生成一个向量点，而是把名字 描述 别名都拆开建立语义入口
            points.append(
                {
                    "id": _stable_point_id(
                        "column", column_info.id, "name", column_info.name
                    ),
                    "embedding_text": column_info.name,
                    "payload": asdict(column_info),
                }
            )

            points.append(
                {
                    "id": _stable_point_id(
                        "column",
                        column_info.id,
                        "description",
                        column_info.description,
                    ),
                    "embedding_text": column_info.description,
                    "payload": asdict(column_info),
                }
            )

            for alia in column_info.alias:
                points.append(
                    {
                        "id": _stable_point_id("column", column_info.id, "alias", alia),
                        "embedding_text": alia,
                        "payload": asdict(column_info),
                    }
                )

        # 先把待向量化文本抽出来，再分批调用 Embedding 服务
        # 这样更容易控制单次请求大小
        embeddings: list[list[float]] = []
        embedding_texts = [point["embedding_text"] for point in points]
        # 新版 TEI 按输入条数占用并发许可（MAX_CONCURRENT_REQUESTS=16）
        # 批量过大必现 429，这里留一半余量给并发调用方
        embedding_batch_size = 8
        for i in range(0, len(embedding_texts), embedding_batch_size):
            batch_embedding_texts = embedding_texts[i : i + embedding_batch_size]
            batch_embeddings = await self.embedding_client.aembed_documents(
                batch_embedding_texts
            )
            embeddings.extend(batch_embeddings)

        ids = [point["id"] for point in points]
        payloads = [point["payload"] for point in points]

        if target_collection is None:
            await self.column_qdrant_repository.upsert(ids, embeddings, payloads)
        else:
            await self.column_qdrant_repository.upsert(
                ids,
                embeddings,
                payloads,
                collection_name=target_collection,
            )
        return len(points)

    async def _save_value_info_to_es(
        self,
        meta_config: MetaConfig,
        column_infos: list[ColumnInfo],
        target_index: str | None = None,
    ):
        """确保索引存储确实存在"""
        if target_index is None:
            await self.value_es_repository.ensure_index()
        else:
            await self.value_es_repository.ensure_index(index_name=target_index)

        # 不是所有字段都要同步真实值，是否同步由配置里的 sync 显式控制
        column2sync: dict[str, bool] = {}
        for table in meta_config.tables:
            for column in table.columns:
                column2sync[f"{table.name}.{column.name}"] = column.sync

        value_infos: list[ValueInfo] = []
        for column_info in column_infos:
            sync = column2sync[column_info.id]
            if sync:
                # 这里拿的是字段真实值全集，不再是第 8 章里的少量 examples
                current_column_values = (
                    await self.dw_mysql_repository.get_column_values(
                        column_info.table_id, column_info.name, 100000
                    )
                )
                current_values_infos = [
                    ValueInfo(
                        id=f"{column_info.id}.{current_column_value}",
                        value=current_column_value,
                        column_id=column_info.id,
                    )
                    for current_column_value in current_column_values
                ]
                value_infos.extend(current_values_infos)

        if target_index is None:
            await self.value_es_repository.index(value_infos)
        else:
            await self.value_es_repository.index(value_infos, index_name=target_index)
        return len(value_infos)

    async def _save_metrics_to_meta_db(
        self, meta_config: MetaConfig
    ) -> list[MetricInfo]:
        """把配置里的指标信息和字段依赖关系写入 Meta MySQL"""
        metric_infos: list[MetricInfo] = []
        column_metrics: list[ColumnMetric] = []

        for metric in meta_config.metrics:
            # MetricInfo 表达指标本身，当前直接用指标名作为稳定业务 id
            metric_info = MetricInfo(
                id=metric.name,
                name=metric.name,
                description=metric.description,
                relevant_columns=metric.relevant_columns,
                alias=metric.alias,
            )
            metric_infos.append(metric_info)
            for column in metric.relevant_columns:
                # ColumnMetric 单独表达“某个指标依赖某个字段”这层关系
                column_metric = ColumnMetric(column_id=column, metric_id=metric.name)
                column_metrics.append(column_metric)

        # 指标本身和字段关系要放在同一笔事务里，避免只写入其中一部分
        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.save_metric_infos(metric_infos)
            await self.meta_mysql_repository.save_column_metrics(column_metrics)

        return metric_infos

    async def _save_metrics_to_qdrant(
        self,
        metric_infos: list[MetricInfo],
        target_collection: str | None = None,
    ):
        """把指标元数据继续推进成可语义检索的 Qdrant 向量点"""
        if target_collection is None:
            await self.metric_qdrant_repository.ensure_collection()
        else:
            await self.metric_qdrant_repository.ensure_collection(
                collection_name=target_collection
            )

        points: list[dict] = []
        for metric_info in metric_infos:
            # 和字段一样，一个指标也会拆成名字 描述 别名这几类语义入口
            points.append(
                {
                    "id": _stable_point_id(
                        "metric", metric_info.id, "name", metric_info.name
                    ),
                    "embedding_text": metric_info.name,
                    "payload": asdict(metric_info),
                }
            )

            points.append(
                {
                    "id": _stable_point_id(
                        "metric",
                        metric_info.id,
                        "description",
                        metric_info.description,
                    ),
                    "embedding_text": metric_info.description,
                    "payload": asdict(metric_info),
                }
            )

            for alia in metric_info.alias:
                points.append(
                    {
                        "id": _stable_point_id("metric", metric_info.id, "alias", alia),
                        "embedding_text": alia,
                        "payload": asdict(metric_info),
                    }
                )

        # 先把待向量化文本抽出来，再分批调用 Embedding 服务
        # 返回的 embeddings 要继续和前面的 id payload 按顺序对齐
        embeddings: list[list[float]] = []
        embedding_texts = [point["embedding_text"] for point in points]
        # 新版 TEI 按输入条数占用并发许可（MAX_CONCURRENT_REQUESTS=16）
        # 批量过大必现 429，这里留一半余量给并发调用方
        embedding_batch_size = 8
        for i in range(0, len(embedding_texts), embedding_batch_size):
            batch_embedding_texts = embedding_texts[i : i + embedding_batch_size]
            batch_embeddings = await self.embedding_client.aembed_documents(
                batch_embedding_texts
            )
            embeddings.extend(batch_embeddings)

        ids = [point["id"] for point in points]
        payloads = [point["payload"] for point in points]

        if target_collection is None:
            await self.metric_qdrant_repository.upsert(ids, embeddings, payloads)
        else:
            await self.metric_qdrant_repository.upsert(
                ids,
                embeddings,
                payloads,
                collection_name=target_collection,
            )
        return len(points)

    async def build(self, config_path: Path, release_version: str | None = None):
        """串行执行当前进程内的元数据构建。"""
        async with self._build_lock:
            return await self._build_unlocked(config_path, release_version)

    async def _build_unlocked(
        self, config_path: Path, release_version: str | None = None
    ):
        """构建元数据索引；传入版本时先 staging，校验后切换 alias。"""
        context = OmegaConf.load(config_path)
        schema = OmegaConf.structured(MetaConfig)
        meta_config: MetaConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))

        staged_indexes = []
        staging_resources = []
        commit_started = False
        active_column_target = None
        active_value_target = None
        active_metric_target = None
        try:
            if release_version:
                if meta_config.tables:
                    column_staging = (
                        await self.column_qdrant_repository.create_physical_collection(
                            release_version
                        )
                    )
                    staging_resources.append(
                        (self.column_qdrant_repository, column_staging)
                    )
                    column_previous = await self.column_qdrant_repository.ensure_alias()
                    if column_staging == column_previous:
                        staging_resources.pop()
                        raise ValueError(
                            "release version already points to column alias"
                        )
                    value_staging = (
                        await self.value_es_repository.create_physical_index(
                            release_version
                        )
                    )
                    staging_resources.append((self.value_es_repository, value_staging))
                    value_previous = await self.value_es_repository.ensure_alias()
                    if value_staging == value_previous:
                        staging_resources.pop()
                        raise ValueError(
                            "release version already points to value alias"
                        )
                    staged_indexes.extend(
                        [
                            (
                                "column",
                                self.column_qdrant_repository,
                                column_staging,
                                column_previous,
                            ),
                            (
                                "value",
                                self.value_es_repository,
                                value_staging,
                                value_previous,
                            ),
                        ]
                    )
                if meta_config.metrics:
                    metric_staging = (
                        await self.metric_qdrant_repository.create_physical_collection(
                            release_version
                        )
                    )
                    staging_resources.append(
                        (self.metric_qdrant_repository, metric_staging)
                    )
                    metric_previous = await self.metric_qdrant_repository.ensure_alias()
                    if metric_staging == metric_previous:
                        staging_resources.pop()
                        raise ValueError(
                            "release version already points to metric alias"
                        )
                    staged_indexes.append(
                        (
                            "metric",
                            self.metric_qdrant_repository,
                            metric_staging,
                            metric_previous,
                        )
                    )
            else:
                if meta_config.tables:
                    active_column_target = (
                        await self.column_qdrant_repository.get_alias_target()
                    )
                    active_value_target = (
                        await self.value_es_repository.get_alias_target()
                    )
                if meta_config.metrics:
                    active_metric_target = (
                        await self.metric_qdrant_repository.get_alias_target()
                    )

            if meta_config.tables:
                column_infos = await self._save_tables_to_meta_db(meta_config)
                logger.info("保存表信息和字段信息到 Meta MySQL")
                column_index = (
                    next(item for item in staged_indexes if item[0] == "column")
                    if release_version
                    else None
                )
                column_count = await self._save_column_info_to_qdrant(
                    column_infos,
                    target_collection=(
                        column_index[2] if column_index else active_column_target
                    ),
                )
                logger.info("为字段信息建立向量索引")
                if (
                    column_index
                    and column_count
                    != await self.column_qdrant_repository.count_points(column_index[2])
                ):
                    raise ValueError("column staging point count mismatch")

                value_index = (
                    next(item for item in staged_indexes if item[0] == "value")
                    if release_version
                    else None
                )
                value_count = await self._save_value_info_to_es(
                    meta_config,
                    column_infos,
                    target_index=value_index[2] if value_index else active_value_target,
                )
                logger.info("为字段取值建立全文索引")
                if (
                    value_index
                    and value_count
                    != await self.value_es_repository.count_documents(value_index[2])
                ):
                    raise ValueError("value staging document count mismatch")

            if meta_config.metrics:
                metric_infos = await self._save_metrics_to_meta_db(meta_config)
                logger.info("保存指标信息到数据库成功")
                metric_index = (
                    next(item for item in staged_indexes if item[0] == "metric")
                    if release_version
                    else None
                )
                metric_count = await self._save_metrics_to_qdrant(
                    metric_infos,
                    target_collection=(
                        metric_index[2] if metric_index else active_metric_target
                    ),
                )
                logger.info("为指标信息建立向量索引成功")
                if (
                    metric_index
                    and metric_count
                    != await self.metric_qdrant_repository.count_points(metric_index[2])
                ):
                    raise ValueError("metric staging point count mismatch")

            if release_version and staged_indexes:
                commit_started = True
                await self._commit_staged_indexes(staged_indexes)
        except Exception:
            if not commit_started:
                await self._cleanup_staging_resources(staging_resources)
            raise
