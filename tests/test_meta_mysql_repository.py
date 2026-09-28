import unittest
from unittest.mock import AsyncMock

from sqlalchemy.dialects import mysql

from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository


class MetaMySQLRepositoryUpsertTest(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_writes_use_mysql_upsert_for_all_entity_types(self):
        session = AsyncMock()
        repository = MetaMySQLRepository(session)

        calls = [
            (
                repository.save_table_infos,
                [
                    TableInfo(
                        id="fact_order",
                        name="fact_order",
                        role="fact",
                        description="订单",
                    )
                ],
            ),
            (
                repository.save_column_infos,
                [
                    ColumnInfo(
                        id="fact_order.order_id",
                        name="order_id",
                        type="varchar",
                        role="primary_key",
                        examples=["1"],
                        description="订单编号",
                        alias=["订单号"],
                        table_id="fact_order",
                    )
                ],
            ),
            (
                repository.save_metric_infos,
                [
                    MetricInfo(
                        id="GMV",
                        name="GMV",
                        description="成交金额",
                        relevant_columns=["fact_order.order_amount"],
                        alias=["销售额"],
                    )
                ],
            ),
            (
                repository.save_column_metrics,
                [ColumnMetric(column_id="fact_order.order_amount", metric_id="GMV")],
            ),
        ]

        for method, entities in calls:
            with self.subTest(method=method.__name__):
                session.execute.reset_mock()
                await method(entities)
                statement = session.execute.await_args.args[0]
                sql = str(statement.compile(dialect=mysql.dialect()))
                self.assertIn("ON DUPLICATE KEY UPDATE", sql)

    async def test_empty_metadata_batches_do_not_execute_sql(self):
        session = AsyncMock()
        repository = MetaMySQLRepository(session)

        await repository.save_table_infos([])

        session.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
