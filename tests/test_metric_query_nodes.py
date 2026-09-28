import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.exceptions import OutputParserException

from app.conf.app_config import app_config
from app.core.query_errors import QueryExecutionError
from app.entities.cube_member import CubeMember
from app.entities.value_info import ValueInfo


def _member(
    name: str,
    member_type: str,
    *,
    data_type: str = "string",
    filterable: bool = False,
    source_column_id: str | None = None,
) -> CubeMember:
    return CubeMember(
        name=name,
        cube_name="ecommerce",
        member_type=member_type,
        data_type=data_type,
        title=f"{name} title",
        description=f"{name} description",
        aliases=[f"{name} alias"],
        ai_context=f"{name} context",
        source_column_id=source_column_id,
        filterable=filterable,
    )


def _members() -> list[CubeMember]:
    return [
        _member("ecommerce.gmv", "measure", data_type="number"),
        _member(
            "ecommerce.region_name",
            "dimension",
            filterable=True,
            source_column_id="dim_region.region_name",
        ),
        _member(
            "ecommerce.channel_name",
            "dimension",
            filterable=True,
            source_column_id="dim_channel.channel_name",
        ),
        _member("ecommerce.order_date", "time_dimension", data_type="time"),
    ]


def _state(raw: object | None = None) -> dict:
    members = _members()
    return {
        "query": "按地区统计销售额",
        "retrieved_cube_measures": [members[0]],
        "retrieved_cube_dimensions": members[1:],
        "cube_member_catalog": {member.name: member for member in members},
        "retrieved_value_infos": [
            ValueInfo(
                id="region-east",
                column_id="dim_region.region_name",
                value="华东",
            ),
            ValueInfo(
                id="unrelated",
                column_id="dim_customer.customer_name",
                value="不应绑定",
            ),
        ],
        "metric_query_raw": raw,
    }


def _matched_raw() -> dict:
    return {
        "status": "matched",
        "query": {
            "measures": ["ecommerce.gmv"],
            "dimensions": ["ecommerce.region_name"],
            "filters": [
                {
                    "member": "ecommerce.region_name",
                    "operator": "equals",
                    "values": ["华东"],
                }
            ],
            "order_by": [{"member": "ecommerce.gmv", "direction": "desc"}],
            "limit": 100,
        },
    }


class GenerateMetricQueryTest(unittest.IsolatedAsyncioTestCase):
    async def test_valid_json_is_shape_validated_with_one_model_call(self):
        from app.agent.nodes.generate_metric_query import generate_metric_query

        model = AsyncMock(return_value=_matched_raw())
        events = []
        with patch(
            "app.agent.nodes.generate_metric_query.invoke_metric_query_model", model
        ):
            result = await generate_metric_query(
                _state(), SimpleNamespace(stream_writer=events.append)
            )

        self.assertEqual(_matched_raw(), result["metric_query_raw"])
        self.assertEqual(1, model.await_count)
        self.assertEqual("running", events[0]["status"])
        self.assertEqual("success", events[-1]["status"])

    async def test_approved_unmatched_json_is_preserved(self):
        from app.agent.nodes.generate_metric_query import generate_metric_query

        unmatched = {"status": "unmatched", "reason": "unsupported_analysis"}
        model = AsyncMock(return_value=unmatched)
        with patch(
            "app.agent.nodes.generate_metric_query.invoke_metric_query_model", model
        ):
            result = await generate_metric_query(
                _state(), SimpleNamespace(stream_writer=lambda event: None)
            )

        self.assertEqual(unmatched, result["metric_query_raw"])
        self.assertEqual(1, model.await_count)

    async def test_invalid_first_output_is_repaired_exactly_once(self):
        from app.agent.nodes.generate_metric_query import generate_metric_query

        invalid = {"status": "matched", "query": {"measures": []}}
        model = AsyncMock(side_effect=[invalid, _matched_raw()])
        with patch(
            "app.agent.nodes.generate_metric_query.invoke_metric_query_model", model
        ):
            result = await generate_metric_query(
                _state(), SimpleNamespace(stream_writer=lambda event: None)
            )

        self.assertEqual(_matched_raw(), result["metric_query_raw"])
        self.assertEqual(2, model.await_count)
        repair_prompt = model.await_args_list[1].args[0]
        self.assertIn('"measures": []', repair_prompt)
        self.assertIn("between 1 and 3", repair_prompt)
        self.assertEqual(
            model.await_args_list[0].args[0].count("ecommerce.gmv"),
            repair_prompt.count("ecommerce.gmv"),
        )

    async def test_invalid_second_output_raises_without_third_call(self):
        from app.agent.nodes.generate_metric_query import generate_metric_query

        invalid = {"status": "matched", "query": {"measures": []}}
        model = AsyncMock(side_effect=[invalid, invalid, AssertionError("third call")])
        with patch(
            "app.agent.nodes.generate_metric_query.invoke_metric_query_model", model
        ):
            with self.assertRaises(QueryExecutionError) as raised:
                await generate_metric_query(
                    _state(), SimpleNamespace(stream_writer=lambda event: None)
                )

        self.assertEqual("invalid_model_output", raised.exception.code)
        self.assertFalse(raised.exception.retryable)
        self.assertEqual(2, model.await_count)

    async def test_infrastructure_error_propagates_unchanged_without_retry(self):
        from app.agent.nodes.generate_metric_query import generate_metric_query

        infrastructure_error = RuntimeError("model transport unavailable")
        model = AsyncMock(side_effect=infrastructure_error)
        with patch(
            "app.agent.nodes.generate_metric_query.invoke_metric_query_model", model
        ):
            with self.assertRaises(RuntimeError) as raised:
                await generate_metric_query(
                    _state(), SimpleNamespace(stream_writer=lambda event: None)
                )

        self.assertIs(infrastructure_error, raised.exception)
        self.assertEqual(1, model.await_count)

    async def test_parser_error_is_repaired_once(self):
        from app.agent.nodes.generate_metric_query import generate_metric_query

        parser_error = OutputParserException("invalid JSON", llm_output="not-json")
        model = AsyncMock(side_effect=[parser_error, _matched_raw()])
        with patch(
            "app.agent.nodes.generate_metric_query.invoke_metric_query_model", model
        ):
            result = await generate_metric_query(
                _state(), SimpleNamespace(stream_writer=lambda event: None)
            )

        self.assertEqual(_matched_raw(), result["metric_query_raw"])
        self.assertEqual(2, model.await_count)

    async def test_prompt_is_constrained_and_maps_values_by_source_column(self):
        from app.agent.nodes.generate_metric_query import generate_metric_query

        model = AsyncMock(
            return_value={"status": "unmatched", "reason": "unsupported_analysis"}
        )
        with patch(
            "app.agent.nodes.generate_metric_query.invoke_metric_query_model", model
        ):
            await generate_metric_query(
                _state(), SimpleNamespace(stream_writer=lambda event: None)
            )

        prompt = model.await_args.args[0]
        required_lines = [
            "You map a Chinese analytics question to the supplied governed members.",
            "Return one JSON object only. Do not return SQL, Markdown, or explanations.",
            "Use only supplied measure candidates. Use only supplied dimensions and time dimensions.",
            "If the request cannot be represented, return status=unmatched with exactly one approved reason.",
            "Filters are AND-only. Time ranges use only approved presets or YYYY-MM-DD bounds.",
            "Time range type must be exactly preset or absolute; never use month, quarter, or date as the type.",
            "For an explicit calendar period such as 2025 Q1, use type=absolute with start=2025-01-01 and end=2025-03-31.",
            "A grouping phrase such as 按月 sets granularity only; do not infer a date range unless the user states one.",
        ]
        for line in required_lines:
            self.assertIn(line, prompt)
        self.assertRegex(
            prompt,
            re.compile(
                r'"name": "ecommerce\.region_name".*?'
                r'"recalled_values": \[\s*"华东"\s*\]',
                re.DOTALL,
            ),
        )
        channel_section = prompt.split('"name": "ecommerce.channel_name"', 1)[1]
        channel_section = channel_section.split('"name": "ecommerce.order_date"', 1)[0]
        self.assertNotIn("华东", channel_section)
        self.assertNotIn("不应绑定", prompt)


class ValidateMetricQueryTest(unittest.IsolatedAsyncioTestCase):
    async def test_configured_limit_constrains_prompt_generation_and_validation(self):
        from app.agent.nodes.generate_metric_query import generate_metric_query
        from app.agent.nodes.validate_metric_query import validate_metric_query

        over_limit = _matched_raw()
        over_limit["query"]["limit"] = 8
        model = AsyncMock(side_effect=[over_limit, over_limit])

        with patch.object(app_config.cube, "max_limit", 7):
            with patch(
                "app.agent.nodes.generate_metric_query.invoke_metric_query_model",
                model,
            ):
                with self.assertRaises(QueryExecutionError) as generation_error:
                    await generate_metric_query(
                        _state(), SimpleNamespace(stream_writer=lambda event: None)
                    )

            with self.assertRaises(QueryExecutionError) as validation_error:
                await validate_metric_query(
                    _state(over_limit),
                    SimpleNamespace(stream_writer=lambda event: None),
                )

        self.assertEqual("invalid_model_output", generation_error.exception.code)
        self.assertEqual(2, model.await_count)
        self.assertIn("Maximum query limit: 7", model.await_args_list[0].args[0])
        self.assertIn('"limit": 7', model.await_args_list[0].args[0])
        self.assertEqual("invalid_model_output", validation_error.exception.code)

    async def test_matched_result_routes_metric_after_deterministic_validation(self):
        from app.agent.nodes.validate_metric_query import validate_metric_query

        events = []
        result = await validate_metric_query(
            _state(_matched_raw()), SimpleNamespace(stream_writer=events.append)
        )

        self.assertEqual("metric", result["query_mode"])
        self.assertEqual("governed_measure_matched", result["route_reason"])
        self.assertEqual("matched", result["metric_query_decision"].status)
        self.assertEqual(["ecommerce.gmv"], result["cube_query"]["measures"])
        self.assertEqual(
            {
                "type": "route",
                "mode": "metric",
                "reason": "governed_measure_matched",
            },
            events[0],
        )
        self.assertEqual("audit", events[1]["type"])
        self.assertEqual(_matched_raw(), events[1]["metric_query"])
        self.assertEqual(result["cube_query"], events[1]["cube_query"])

    async def test_approved_unmatched_result_routes_sql(self):
        from app.agent.nodes.validate_metric_query import validate_metric_query

        events = []
        raw = {"status": "unmatched", "reason": "missing_dimension_mapping"}
        result = await validate_metric_query(
            _state(raw), SimpleNamespace(stream_writer=events.append)
        )

        self.assertEqual("sql", result["query_mode"])
        self.assertEqual("missing_dimension_mapping", result["route_reason"])
        self.assertEqual("unmatched", result["metric_query_decision"].status)
        self.assertNotIn("cube_query", result)
        self.assertEqual(
            {
                "type": "route",
                "mode": "sql",
                "reason": "missing_dimension_mapping",
            },
            events[0],
        )
        self.assertEqual("audit", events[1]["type"])
        self.assertEqual(raw, events[1]["metric_query"])

    async def test_unknown_member_becomes_non_retryable_query_error_without_route(self):
        from app.agent.nodes.validate_metric_query import validate_metric_query

        raw = _matched_raw()
        raw["query"]["dimensions"] = ["ecommerce.unknown"]
        events = []

        with self.assertRaises(QueryExecutionError) as raised:
            await validate_metric_query(
                _state(raw), SimpleNamespace(stream_writer=events.append)
            )

        self.assertEqual("unknown_member", raised.exception.code)
        self.assertFalse(raised.exception.retryable)
        self.assertEqual([], events)


if __name__ == "__main__":
    unittest.main()
