import copy
import unittest
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from unittest.mock import patch

import app.agent.metric_query as metric_query_module
from app.agent.metric_query import (
    normalize_cube_result,
    resolve_time_range,
    to_cube_query,
    validate_metric_query_result,
    validate_metric_query_shape,
)
from app.core.query_errors import QueryExecutionError
from app.entities.cube_member import CubeMember
from app.entities.metric_query import MetricQueryValidationError


def _member(
    name: str,
    member_type: str,
    *,
    data_type: str = "string",
    filterable: bool = False,
) -> CubeMember:
    return CubeMember(
        name=name,
        cube_name="ecommerce",
        member_type=member_type,
        data_type=data_type,
        title=name,
        description=name,
        aliases=[],
        ai_context="",
        source_column_id=None,
        filterable=filterable,
    )


class MetricQueryValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        members = [
            _member("ecommerce.gmv", "measure", data_type="number"),
            _member("ecommerce.order_count", "measure", data_type="number"),
            _member("ecommerce.region_name", "dimension", filterable=True),
            _member("ecommerce.province", "dimension", filterable=True),
            _member(
                "ecommerce.order_amount",
                "dimension",
                data_type="number",
                filterable=True,
            ),
            _member(
                "ecommerce.is_member",
                "dimension",
                data_type="boolean",
                filterable=True,
            ),
            _member(
                "ecommerce.created_at",
                "dimension",
                data_type="time",
                filterable=True,
            ),
            _member("ecommerce.brand", "dimension", filterable=False),
            _member("ecommerce.order_date", "time_dimension"),
        ]
        self.catalog = {member.name: member for member in members}
        self.candidates = {"ecommerce.gmv"}

    @staticmethod
    def valid_raw() -> dict:
        return {
            "status": "matched",
            "query": {
                "measures": ["ecommerce.gmv"],
                "dimensions": ["ecommerce.region_name"],
                "filters": [
                    {
                        "member": "ecommerce.region_name",
                        "operator": "equals",
                        "values": ["east"],
                    }
                ],
                "time": {
                    "dimension": "ecommerce.order_date",
                    "range": {"type": "preset", "value": "last_quarter"},
                    "granularity": "month",
                },
                "order_by": [{"member": "ecommerce.gmv", "direction": "desc"}],
                "limit": 100,
            },
        }

    def assert_validation_error(self, raw: object, code: str) -> None:
        with self.assertRaises(MetricQueryValidationError) as raised:
            validate_metric_query_result(
                raw,
                self.candidates,
                self.catalog,
                max_limit=500,
            )
        self.assertEqual(code, raised.exception.code)

    def test_required_rejection_matrix(self) -> None:
        cases: list[tuple[str, object, str]] = []

        raw = self.valid_raw()
        raw["extra"] = True
        cases.append(("extra top-level key", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["status"] = "maybe"
        cases.append(("unknown status", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["measures"] = []
        cases.append(("zero measures", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["measures"] = ["m1", "m2", "m3", "m4"]
        cases.append(("four measures", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["dimensions"] = [f"d{index}" for index in range(6)]
        cases.append(("six dimensions", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["filters"] = [
            {
                "member": f"d{index}",
                "operator": "equals",
                "values": ["x"],
            }
            for index in range(11)
        ]
        cases.append(("eleven filters", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["filters"][0]["values"] = list(range(21))
        cases.append(("twenty-one filter values", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["time"] = [raw["query"]["time"], raw["query"]["time"]]
        cases.append(("time represented as a list", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["order_by"] = [
            {"member": f"d{index}", "direction": "asc"} for index in range(4)
        ]
        cases.append(("four order items", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["limit"] = 0
        cases.append(("limit zero", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["limit"] = 501
        cases.append(("limit over maximum", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["dimensions"] = ["ecommerce.missing"]
        cases.append(("unknown member", raw, "unknown_member"))

        raw = self.valid_raw()
        raw["query"]["measures"] = ["ecommerce.order_count"]
        raw["query"]["order_by"] = []
        cases.append(("non-candidate measure", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["dimensions"] = ["ecommerce.gmv"]
        raw["query"]["filters"] = []
        cases.append(("measure used as dimension", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["filters"] = [
            {
                "member": "ecommerce.brand",
                "operator": "equals",
                "values": ["x"],
            }
        ]
        cases.append(("non-filterable member", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["filters"][0]["operator"] = "greater_than"
        cases.append(("comparison on string member", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["filters"][0] = {
            "member": "ecommerce.region_name",
            "operator": "is_set",
            "values": ["x"],
        }
        cases.append(("values on is_set", raw, "invalid_model_output"))

        raw = self.valid_raw()
        raw["query"]["order_by"] = [
            {"member": "ecommerce.province", "direction": "asc"}
        ]
        cases.append(("order by unselected member", raw, "invalid_model_output"))

        for name, raw, code in cases:
            with self.subTest(name=name):
                self.assert_validation_error(raw, code)

    def test_strict_shape_rejects_nested_extra_keys_and_type_coercion(self) -> None:
        cases: list[tuple[str, dict]] = []
        for path in ("query", "filter", "order", "time", "range"):
            raw = self.valid_raw()
            target = {
                "query": raw["query"],
                "filter": raw["query"]["filters"][0],
                "order": raw["query"]["order_by"][0],
                "time": raw["query"]["time"],
                "range": raw["query"]["time"]["range"],
            }[path]
            target["extra"] = "rejected"
            cases.append((f"extra key in {path}", raw))

        raw = self.valid_raw()
        raw["query"]["limit"] = True
        cases.append(("boolean limit", raw))

        raw = self.valid_raw()
        raw["query"]["limit"] = "100"
        cases.append(("string limit", raw))

        raw = self.valid_raw()
        raw["query"]["filters"][0]["values"] = [True]
        cases.append(("boolean filter value", raw))

        raw = self.valid_raw()
        raw["query"]["measures"] = [" ecommerce.gmv "]
        cases.append(("whitespace-padded member", raw))

        for name, raw in cases:
            with self.subTest(name=name):
                self.assert_validation_error(raw, "invalid_model_output")

    def test_shape_rejects_duplicates_and_invalid_absolute_dates(self) -> None:
        cases: list[tuple[str, dict]] = []

        raw = self.valid_raw()
        raw["query"]["measures"] *= 2
        cases.append(("duplicate measures", raw))

        raw = self.valid_raw()
        raw["query"]["dimensions"] *= 2
        cases.append(("duplicate dimensions", raw))

        raw = self.valid_raw()
        raw["query"]["filters"] *= 2
        cases.append(("duplicate filter members", raw))

        raw = self.valid_raw()
        raw["query"]["order_by"] *= 2
        cases.append(("duplicate order members", raw))

        for start, end, name in [
            ("2026-02-29", "2026-03-01", "nonexistent date"),
            ("2026-10-01", "2026-09-30", "reversed dates"),
            ("2026-9-01", "2026-09-30", "non-ISO date"),
        ]:
            raw = self.valid_raw()
            raw["query"]["time"]["range"] = {
                "type": "absolute",
                "start": start,
                "end": end,
            }
            cases.append((name, raw))

        for name, raw in cases:
            with self.subTest(name=name):
                self.assert_validation_error(raw, "invalid_model_output")

    def test_all_approved_unmatched_reasons_pass(self) -> None:
        reasons = [
            "no_measure_candidate",
            "missing_dimension_mapping",
            "unsupported_analysis",
            "ambiguous_measure",
        ]
        for reason in reasons:
            with self.subTest(reason=reason):
                decision = validate_metric_query_result(
                    {"status": "unmatched", "reason": reason},
                    self.candidates,
                    self.catalog,
                    max_limit=500,
                )
                self.assertEqual("unmatched", decision.status)
                self.assertEqual(reason, decision.reason)
                self.assertIsNone(decision.query)
                self.assertIsNone(decision.cube_query)

    def test_filter_values_must_match_the_member_data_type(self) -> None:
        cases = [
            ("string accepts strings", "ecommerce.region_name", ["east"], True),
            ("string rejects numbers", "ecommerce.region_name", [1], False),
            ("number accepts numbers", "ecommerce.order_amount", [1, 1.5], True),
            ("number rejects strings", "ecommerce.order_amount", ["east"], False),
        ]
        for name, member, values, accepted in cases:
            raw = self.valid_raw()
            raw["query"]["filters"] = [
                {"member": member, "operator": "equals", "values": values}
            ]
            with self.subTest(name=name):
                if accepted:
                    decision = validate_metric_query_result(
                        raw,
                        self.candidates,
                        self.catalog,
                        max_limit=500,
                    )
                    self.assertEqual(tuple(values), decision.query.filters[0].values)
                else:
                    self.assert_validation_error(raw, "invalid_model_output")

    def test_boolean_and_time_filter_types_are_not_supported(self) -> None:
        for member in ("ecommerce.is_member", "ecommerce.created_at"):
            raw = self.valid_raw()
            raw["query"]["filters"] = [{"member": member, "operator": "is_set"}]
            with self.subTest(member=member):
                self.assert_validation_error(raw, "invalid_model_output")

    def test_valid_matched_result_is_frozen_and_contains_cube_query(self) -> None:
        decision = validate_metric_query_result(
            self.valid_raw(),
            self.candidates,
            self.catalog,
            max_limit=500,
            today=date(2026, 9, 28),
        )

        self.assertEqual("matched", decision.status)
        self.assertIsNone(decision.reason)
        self.assertEqual(("ecommerce.gmv",), decision.query.measures)
        self.assertEqual(100, decision.query.limit)
        self.assertEqual(
            ["2026-04-01", "2026-06-30"],
            decision.cube_query["timeDimensions"][0]["dateRange"],
        )
        with self.assertRaises(FrozenInstanceError):
            decision.query.limit = 200

    def test_measure_candidates_are_passed_as_member_names(self) -> None:
        decision = validate_metric_query_result(
            self.valid_raw(),
            {"ecommerce.gmv"},
            self.catalog,
            max_limit=500,
            today=date(2026, 9, 28),
        )

        self.assertEqual("matched", decision.status)
        self.assertEqual(("ecommerce.gmv",), decision.query.measures)

    def test_omitted_today_uses_the_asia_shanghai_clock(self) -> None:
        observed_timezones = []

        class FrozenDateTime:
            @classmethod
            def now(cls, timezone):
                observed_timezones.append(timezone)
                return datetime(2026, 9, 28, 0, 30, tzinfo=timezone)

        raw = self.valid_raw()
        raw["query"]["time"]["range"] = {"type": "preset", "value": "today"}
        with patch.object(metric_query_module, "datetime", FrozenDateTime, create=True):
            decision = validate_metric_query_result(
                raw,
                self.candidates,
                self.catalog,
                max_limit=500,
            )

        self.assertEqual(
            ["Asia/Shanghai"],
            [timezone.tzname(None) for timezone in observed_timezones],
        )
        self.assertEqual(
            ["2026-09-28", "2026-09-28"],
            decision.cube_query["timeDimensions"][0]["dateRange"],
        )

    def test_validate_shape_returns_an_independent_dict(self) -> None:
        raw = self.valid_raw()
        validated = validate_metric_query_shape(raw, max_limit=500)

        self.assertEqual(raw, validated)
        self.assertIsNot(raw, validated)
        self.assertIsNot(raw["query"], validated["query"])

    def test_time_accepts_granularity_without_a_range(self) -> None:
        raw = self.valid_raw()
        raw["query"]["time"] = {
            "dimension": "ecommerce.order_date",
            "granularity": "month",
        }

        decision = validate_metric_query_result(
            raw,
            self.candidates,
            self.catalog,
            max_limit=500,
            today=date(2026, 9, 28),
        )

        self.assertEqual("month", decision.query.time.granularity)
        self.assertIsNone(decision.query.time.range)

    def test_time_rejects_an_object_without_range_or_granularity(self) -> None:
        raw = self.valid_raw()
        raw["query"]["time"] = {"dimension": "ecommerce.order_date"}

        self.assert_validation_error(raw, "invalid_model_output")


class MetricQueryTimeTest(unittest.TestCase):
    def test_presets_use_inclusive_calendar_ranges(self) -> None:
        today = date(2026, 9, 28)
        expected = {
            "today": ("2026-09-28", "2026-09-28"),
            "yesterday": ("2026-09-27", "2026-09-27"),
            "this_week": ("2026-09-28", "2026-10-04"),
            "last_week": ("2026-09-21", "2026-09-27"),
            "this_month": ("2026-09-01", "2026-09-30"),
            "last_month": ("2026-08-01", "2026-08-31"),
            "this_quarter": ("2026-07-01", "2026-09-30"),
            "last_quarter": ("2026-04-01", "2026-06-30"),
            "this_year": ("2026-01-01", "2026-12-31"),
            "last_year": ("2025-01-01", "2025-12-31"),
            "last_7_days": ("2026-09-22", "2026-09-28"),
            "last_30_days": ("2026-08-30", "2026-09-28"),
            "last_90_days": ("2026-07-01", "2026-09-28"),
        }

        for preset, date_range in expected.items():
            with self.subTest(preset=preset):
                self.assertEqual(
                    date_range,
                    resolve_time_range({"type": "preset", "value": preset}, today),
                )

    def test_absolute_range_is_preserved(self) -> None:
        self.assertEqual(
            ("2024-02-29", "2024-03-01"),
            resolve_time_range(
                {
                    "type": "absolute",
                    "start": "2024-02-29",
                    "end": "2024-03-01",
                },
                date(2026, 9, 28),
            ),
        )


class CubeQueryAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        validation = MetricQueryValidationTest(methodName="runTest")
        validation.setUp()
        self.catalog = validation.catalog
        self.candidates = validation.candidates
        self.raw = validation.valid_raw()

    def validated_query(self, raw: dict | None = None):
        return validate_metric_query_result(
            raw or self.raw,
            self.candidates,
            self.catalog,
            max_limit=500,
            today=date(2026, 9, 28),
        ).query

    def test_adapter_emits_deterministic_cube_query(self) -> None:
        query = self.validated_query()

        result = to_cube_query(query, self.catalog, date(2026, 9, 28))

        self.assertEqual(
            {
                "measures": ["ecommerce.gmv"],
                "dimensions": ["ecommerce.region_name"],
                "filters": [
                    {
                        "member": "ecommerce.region_name",
                        "operator": "equals",
                        "values": ["east"],
                    }
                ],
                "timeDimensions": [
                    {
                        "dimension": "ecommerce.order_date",
                        "dateRange": ["2026-04-01", "2026-06-30"],
                        "granularity": "month",
                    }
                ],
                "order": {"ecommerce.gmv": "desc"},
                "limit": 100,
                "timezone": "Asia/Shanghai",
            },
            result,
        )

    def test_adapter_maps_operators_and_omits_values_for_set_operators(self) -> None:
        expected = {
            "equals": "equals",
            "not_equals": "notEquals",
            "contains": "contains",
            "not_contains": "notContains",
            "greater_than": "gt",
            "greater_than_or_equal": "gte",
            "less_than": "lt",
            "less_than_or_equal": "lte",
            "is_set": "set",
            "is_not_set": "notSet",
        }
        for operator, cube_operator in expected.items():
            raw = copy.deepcopy(self.raw)
            numeric = operator in {
                "greater_than",
                "greater_than_or_equal",
                "less_than",
                "less_than_or_equal",
            }
            raw["query"]["filters"][0]["member"] = (
                "ecommerce.order_amount" if numeric else "ecommerce.region_name"
            )
            raw["query"]["filters"][0]["operator"] = operator
            if operator in {"is_set", "is_not_set"}:
                del raw["query"]["filters"][0]["values"]
            elif numeric:
                raw["query"]["filters"][0]["values"] = [100]

            with self.subTest(operator=operator):
                cube_query = to_cube_query(
                    self.validated_query(raw),
                    self.catalog,
                    date(2026, 9, 28),
                )
                cube_filter = cube_query["filters"][0]
                self.assertEqual(cube_operator, cube_filter["operator"])
                self.assertEqual(
                    operator not in {"is_set", "is_not_set"},
                    "values" in cube_filter,
                )

    def test_adapter_uses_default_limit_and_omits_empty_optional_sections(self) -> None:
        raw = self.raw
        query = raw["query"]
        query["dimensions"] = []
        query["filters"] = []
        query.pop("time")
        query["order_by"] = []
        query.pop("limit")

        cube_query = to_cube_query(
            self.validated_query(raw),
            self.catalog,
            date(2026, 9, 28),
        )

        self.assertEqual(
            {
                "measures": ["ecommerce.gmv"],
                "limit": 100,
                "timezone": "Asia/Shanghai",
            },
            cube_query,
        )

    def test_adapter_omits_date_range_for_granularity_only_time(self) -> None:
        raw = self.raw
        raw["query"]["time"] = {
            "dimension": "ecommerce.order_date",
            "granularity": "month",
        }

        cube_query = to_cube_query(
            self.validated_query(raw),
            self.catalog,
            date(2026, 9, 28),
        )

        self.assertEqual(
            [
                {
                    "dimension": "ecommerce.order_date",
                    "granularity": "month",
                }
            ],
            cube_query["timeDimensions"],
        )


class CubeResultNormalizationTest(unittest.TestCase):
    def test_returns_rows_from_top_level_data_without_annotations(self) -> None:
        rows = [{"ecommerce.gmv": "12.50"}, {"ecommerce.gmv": "8.00"}]

        result = normalize_cube_result(
            {
                "query": {"measures": ["ecommerce.gmv"]},
                "data": rows,
                "annotation": {"measures": {}},
                "lastRefreshTime": "2026-09-28T00:00:00.000Z",
            }
        )

        self.assertEqual(rows, result)
        self.assertIsNot(rows, result)

    def test_invalid_cube_responses_raise_retryable_unavailable(self) -> None:
        cases = [
            ("non-object", []),
            ("missing data", {}),
            ("data is not a list", {"data": {}}),
            ("row is not an object", {"data": [1]}),
            ("old results envelope", {"results": [{"data": []}]}),
        ]
        for name, response in cases:
            with self.subTest(name=name):
                with self.assertRaises(QueryExecutionError) as raised:
                    normalize_cube_result(response)
                self.assertEqual("cube_unavailable", raised.exception.code)
                self.assertTrue(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
