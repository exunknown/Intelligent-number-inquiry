import unittest
from unittest.mock import AsyncMock

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.services.meta_knowledge_service import MetaKnowledgeService


class MetaKnowledgeStablePointIdsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.column_repository = AsyncMock()
        self.metric_repository = AsyncMock()
        self.embedding_client = AsyncMock()
        self.embedding_client.aembed_documents.side_effect = lambda texts: [
            [float(index)] for index, _ in enumerate(texts)
        ]
        self.service = MetaKnowledgeService(
            meta_mysql_repository=AsyncMock(),
            dw_mysql_repository=AsyncMock(),
            column_qdrant_repository=self.column_repository,
            embedding_client=self.embedding_client,
            value_es_repository=AsyncMock(),
            metric_qdrant_repository=self.metric_repository,
        )

    async def test_repeated_column_indexing_reuses_the_same_point_ids(self):
        column = ColumnInfo(
            id="fact_order.order_amount",
            name="order_amount",
            type="decimal",
            role="measure",
            examples=[100],
            description="订单金额",
            alias=["销售额"],
            table_id="fact_order",
        )

        await self.service._save_column_info_to_qdrant([column])
        await self.service._save_column_info_to_qdrant([column])

        first_ids = self.column_repository.upsert.await_args_list[0].args[0]
        second_ids = self.column_repository.upsert.await_args_list[1].args[0]
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), len(set(first_ids)))

    async def test_repeated_metric_indexing_reuses_the_same_point_ids(self):
        metric = MetricInfo(
            id="GMV",
            name="GMV",
            description="成交金额",
            relevant_columns=["fact_order.order_amount"],
            alias=["销售额"],
        )

        await self.service._save_metrics_to_qdrant([metric])
        await self.service._save_metrics_to_qdrant([metric])

        first_ids = self.metric_repository.upsert.await_args_list[0].args[0]
        second_ids = self.metric_repository.upsert.await_args_list[1].args[0]
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), len(set(first_ids)))


if __name__ == "__main__":
    unittest.main()
