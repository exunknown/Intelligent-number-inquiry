import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.query_errors import QueryExecutionError
from app.entities.column_info import ColumnInfo
from app.entities.cube_member import CubeMember
from app.entities.table_info import TableInfo


class _FakeCubeRepository:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def load(self, query):
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.response


class _FailingDWRepository:
    def __init__(self):
        self.calls = []

    async def run(self, sql):
        self.calls.append(sql)
        raise AssertionError("Cube execution must not call the SQL repository")


class ExecuteCubeQueryTest(unittest.IsolatedAsyncioTestCase):
    async def test_loads_cube_query_and_emits_verified_metric_result(self):
        from app.agent.nodes.execute_cube_query import execute_cube_query

        cube_query = {"measures": ["ecommerce.gmv"]}
        cube_repository = _FakeCubeRepository(
            response={
                "query": cube_query,
                "data": [{"ecommerce.gmv": "123.45"}],
                "annotation": {"measures": {}},
            }
        )
        dw_repository = _FailingDWRepository()
        events = []
        runtime = SimpleNamespace(
            context={
                "cube_repository": cube_repository,
                "dw_mysql_repository": dw_repository,
            },
            stream_writer=events.append,
        )

        result = await execute_cube_query({"cube_query": cube_query}, runtime)

        self.assertIsNone(result)
        self.assertEqual([cube_query], cube_repository.calls)
        self.assertEqual([], dw_repository.calls)
        self.assertEqual(
            {
                "type": "result",
                "data": [{"ecommerce.gmv": "123.45"}],
                "source": "metric",
                "verified": True,
                "warning": None,
            },
            events[-1],
        )
        self.assertEqual(
            [
                {
                    "type": "progress",
                    "step": "执行指标查询",
                    "status": "running",
                },
                {
                    "type": "progress",
                    "step": "执行指标查询",
                    "status": "success",
                },
            ],
            [event for event in events if event["type"] == "progress"],
        )

    async def test_cube_errors_propagate_without_sql_fallback(self):
        from app.agent.nodes.execute_cube_query import execute_cube_query

        for code in (
            "cube_timeout",
            "cube_unauthorized",
            "cube_unavailable",
            "metadata_out_of_sync",
        ):
            with self.subTest(code=code):
                error = QueryExecutionError(code, f"{code} message", False)
                cube_repository = _FakeCubeRepository(error=error)
                dw_repository = _FailingDWRepository()
                events = []
                runtime = SimpleNamespace(
                    context={
                        "cube_repository": cube_repository,
                        "dw_mysql_repository": dw_repository,
                    },
                    stream_writer=events.append,
                )

                with self.assertRaises(QueryExecutionError) as raised:
                    await execute_cube_query(
                        {"cube_query": {"measures": ["ecommerce.gmv"]}}, runtime
                    )

                self.assertIs(error, raised.exception)
                self.assertEqual([], dw_repository.calls)
                self.assertEqual("error", events[-1]["status"])


class SQLResultProvenanceTest(unittest.IsolatedAsyncioTestCase):
    async def test_sql_result_is_unverified_and_warns_for_manual_review(self):
        from app.agent.nodes.run_sql import run_sql

        class _DWRepository:
            async def run(self, sql):
                return [{"sql": sql}]

        events = []
        runtime = SimpleNamespace(
            context={"dw_mysql_repository": _DWRepository()},
            stream_writer=events.append,
        )

        await run_sql({"sql": "SELECT 1"}, runtime)

        self.assertEqual(
            {
                "type": "result",
                "data": [{"sql": "SELECT 1"}],
                "source": "sql",
                "verified": False,
                "warning": "该结果由 Text-to-SQL 生成，未经业务口径验证，请人工核对。",
            },
            events[-1],
        )


class SQLFallbackContextTest(unittest.IsolatedAsyncioTestCase):
    async def test_merge_does_not_require_or_include_legacy_metrics(self):
        from app.agent.nodes.merge_retrieved_info import merge_retrieved_info

        column = ColumnInfo(
            id="fact_order.amount",
            name="amount",
            type="decimal",
            role="measure",
            examples=[],
            description="订单金额",
            alias=[],
            table_id="fact_order",
        )

        class _MetaRepository:
            async def get_key_columns_by_table_id(self, table_id):
                return []

            async def get_table_info_by_id(self, table_id):
                return TableInfo(
                    id=table_id,
                    name="fact_order",
                    role="fact",
                    description="订单事实表",
                )

        events = []
        runtime = SimpleNamespace(
            context={"meta_mysql_repository": _MetaRepository()},
            stream_writer=events.append,
        )

        result = await merge_retrieved_info(
            {
                "retrieved_column_infos": [column],
                "retrieved_value_infos": [],
            },
            runtime,
        )

        self.assertEqual([], result["metric_infos"])
        self.assertEqual([], result["selector_candidates"]["metrics"])
        self.assertEqual(
            ["fact_order"], [item["name"] for item in result["table_infos"]]
        )

    async def test_route_metrics_event_uses_recalled_cube_measure_titles(self):
        from app.agent.nodes.route_selector import route_selector

        measures = [
            CubeMember(
                name="ecommerce.gmv",
                cube_name="ecommerce",
                member_type="measure",
                data_type="number",
                title="成交金额",
                description="成交金额",
                aliases=[],
                ai_context="",
                source_column_id="fact_order.amount",
                filterable=False,
            ),
            CubeMember(
                name="ecommerce.order_count",
                cube_name="ecommerce",
                member_type="measure",
                data_type="number",
                title="",
                description="订单数",
                aliases=[],
                ai_context="",
                source_column_id="fact_order.order_id",
                filterable=False,
            ),
        ]
        events = []
        runtime = SimpleNamespace(stream_writer=events.append)

        with patch("app.agent.nodes.route_selector.should_use_selector") as gate:
            gate.return_value = (False, 1)
            await route_selector(
                {
                    "selector_candidates": {"tables": [], "metrics": [], "values": []},
                    "retrieved_cube_measures": measures,
                },
                runtime,
            )

        self.assertIn(
            {"type": "metrics", "data": ["成交金额", "ecommerce.order_count"]},
            events,
        )

    async def test_apply_selector_metrics_event_uses_recalled_cube_measure_titles(self):
        from app.agent.nodes.apply_selector import apply_selector

        measures = [
            CubeMember(
                name="ecommerce.gmv",
                cube_name="ecommerce",
                member_type="measure",
                data_type="number",
                title="成交金额",
                description="成交金额",
                aliases=[],
                ai_context="",
                source_column_id="fact_order.amount",
                filterable=False,
            ),
            CubeMember(
                name="ecommerce.order_count",
                cube_name="ecommerce",
                member_type="measure",
                data_type="number",
                title="",
                description="订单数",
                aliases=[],
                ai_context="",
                source_column_id="fact_order.order_id",
                filterable=False,
            ),
        ]
        table = {
            "name": "fact_order",
            "role": "fact",
            "description": "订单事实表",
            "columns": [],
        }
        candidates = {
            "tables": [
                {
                    "id": "fact_order",
                    "name": "fact_order",
                    "role": "fact",
                    "description": "订单事实表",
                    "columns": [],
                }
            ],
            "metrics": [],
            "values": [],
        }
        events = []

        await apply_selector(
            {
                "table_infos": [table],
                "selector_candidates": candidates,
                "selector_decision": {
                    "keep_tables": ["fact_order"],
                    "drop_tables": [],
                    "keep_values": [],
                },
                "metric_infos": [],
                "retrieved_cube_measures": measures,
            },
            SimpleNamespace(stream_writer=events.append),
        )

        self.assertIn(
            {"type": "metrics", "data": ["成交金额", "ecommerce.order_count"]},
            events,
        )


if __name__ == "__main__":
    unittest.main()
