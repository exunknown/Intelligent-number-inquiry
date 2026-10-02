"""Strict Metric Query IR validation and deterministic Cube adaptation."""

from calendar import monthrange
from collections.abc import Collection, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import cast

from app.core.query_errors import QueryExecutionError
from app.entities.cube_member import CubeMember
from app.entities.metric_query import (
    AbsoluteTimeRange,
    FilterOperator,
    FilterValue,
    MetricFilter,
    MetricOrder,
    MetricQuery,
    MetricQueryDecision,
    MetricQueryValidationError,
    MetricTime,
    PresetTimeRange,
    SemanticMissReason,
    TimeGranularity,
)

_SEMANTIC_MISS_REASONS = {
    "no_measure_candidate",
    "missing_dimension_mapping",
    "unsupported_analysis",
    "ambiguous_measure",
}
_FILTER_OPERATORS = {
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "is_set",
    "is_not_set",
}
_SET_OPERATORS = {"is_set", "is_not_set"}
_STRING_OPERATORS = {
    "equals",
    "not_equals",
    "contains",
    "not_contains",
    "is_set",
    "is_not_set",
}
_NUMERIC_OPERATORS = {
    "equals",
    "not_equals",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "is_set",
    "is_not_set",
}
_FILTER_VALUE_TYPES = {
    "string": {str},
    "number": {int, float},
}
_GRANULARITIES = {"day", "week", "month", "quarter", "year"}
_PRESET_RANGES = {
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "this_quarter",
    "last_quarter",
    "this_year",
    "last_year",
    "last_7_days",
    "last_30_days",
    "last_90_days",
}
_CUBE_OPERATORS = {
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
_SHANGHAI_TIMEZONE = timezone(timedelta(hours=8), "Asia/Shanghai")


def _invalid(message: str) -> MetricQueryValidationError:
    return MetricQueryValidationError("invalid_model_output", message)


def _require_exact_dict(
    value: object,
    *,
    allowed: set[str],
    required: set[str],
    field: str,
) -> dict:
    if not isinstance(value, dict):
        raise _invalid(f"{field} must be an object")
    keys = set(value)
    if not keys <= allowed or not required <= keys:
        raise _invalid(f"{field} has invalid keys")
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise _invalid(f"{field} must be a non-empty unpadded string")
    return value


def _require_unique_strings(
    value: object,
    *,
    field: str,
    minimum: int,
    maximum: int,
) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise _invalid(f"{field} must contain between {minimum} and {maximum} items")
    result = [_require_string(item, f"{field} item") for item in value]
    if len(set(result)) != len(result):
        raise _invalid(f"{field} must not contain duplicates")
    return result


def _parse_iso_date(value: object, field: str) -> str:
    raw = _require_string(value, field)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise _invalid(f"{field} must be a real ISO date") from exc
    if parsed.isoformat() != raw:
        raise _invalid(f"{field} must use YYYY-MM-DD")
    return raw


def _validate_range_shape(value: object) -> dict:
    range_value = _require_exact_dict(
        value,
        allowed={"type", "value", "start", "end"},
        required={"type"},
        field="query.time.range",
    )
    range_type = range_value["type"]
    if range_type == "preset":
        if set(range_value) != {"type", "value"}:
            raise _invalid("preset range must contain exactly type and value")
        preset = _require_string(range_value["value"], "query.time.range.value")
        if preset not in _PRESET_RANGES:
            raise _invalid("query.time.range.value is unsupported")
        return {"type": "preset", "value": preset}
    if range_type == "absolute":
        if set(range_value) != {"type", "start", "end"}:
            raise _invalid("absolute range must contain exactly type, start, and end")
        start = _parse_iso_date(range_value["start"], "query.time.range.start")
        end = _parse_iso_date(range_value["end"], "query.time.range.end")
        if start > end:
            raise _invalid("query.time.range start must not exceed end")
        return {"type": "absolute", "start": start, "end": end}
    raise _invalid("query.time.range.type is unsupported")


def _validate_filter_shape(value: object, index: int) -> dict:
    field = f"query.filters[{index}]"
    item = _require_exact_dict(
        value,
        allowed={"member", "operator", "values"},
        required={"member", "operator"},
        field=field,
    )
    member = _require_string(item["member"], f"{field}.member")
    operator = _require_string(item["operator"], f"{field}.operator")
    if operator not in _FILTER_OPERATORS:
        raise _invalid(f"{field}.operator is unsupported")
    if operator in _SET_OPERATORS:
        if set(item) != {"member", "operator"}:
            raise _invalid(f"{field} set operators must not include values")
        return {"member": member, "operator": operator}
    if set(item) != {"member", "operator", "values"}:
        raise _invalid(f"{field} requires values")
    values = item["values"]
    if not isinstance(values, list) or not 1 <= len(values) <= 20:
        raise _invalid(f"{field}.values must contain between 1 and 20 items")
    if any(type(item_value) not in {str, int, float} for item_value in values):
        raise _invalid(f"{field}.values must contain scalar values")
    return {"member": member, "operator": operator, "values": list(values)}


def _validate_order_shape(value: object, index: int) -> dict:
    field = f"query.order_by[{index}]"
    item = _require_exact_dict(
        value,
        allowed={"member", "direction"},
        required={"member", "direction"},
        field=field,
    )
    if set(item) != {"member", "direction"}:
        raise _invalid(f"{field} has invalid keys")
    member = _require_string(item["member"], f"{field}.member")
    direction = _require_string(item["direction"], f"{field}.direction")
    if direction not in {"asc", "desc"}:
        raise _invalid(f"{field}.direction is unsupported")
    return {"member": member, "direction": direction}


def _validate_matched_shape(raw: dict, max_limit: int) -> dict:
    if set(raw) != {"status", "query"}:
        raise _invalid("matched output must contain exactly status and query")
    query = _require_exact_dict(
        raw["query"],
        allowed={"measures", "dimensions", "filters", "time", "order_by", "limit"},
        required={"measures"},
        field="query",
    )
    validated: dict = {
        "measures": _require_unique_strings(
            query["measures"], field="query.measures", minimum=1, maximum=3
        )
    }
    if "dimensions" in query:
        validated["dimensions"] = _require_unique_strings(
            query["dimensions"],
            field="query.dimensions",
            minimum=0,
            maximum=5,
        )
    if "filters" in query:
        filters = query["filters"]
        if not isinstance(filters, list) or len(filters) > 10:
            raise _invalid("query.filters must contain between 0 and 10 items")
        validated_filters = [
            _validate_filter_shape(item, index) for index, item in enumerate(filters)
        ]
        filter_members = [item["member"] for item in validated_filters]
        if len(set(filter_members)) != len(filter_members):
            raise _invalid("query.filters must not contain duplicate members")
        validated["filters"] = validated_filters
    if "time" in query:
        time_value = _require_exact_dict(
            query["time"],
            allowed={"dimension", "range", "granularity"},
            required={"dimension"},
            field="query.time",
        )
        validated_time = {
            "dimension": _require_string(
                time_value["dimension"], "query.time.dimension"
            ),
        }
        if "range" not in time_value and "granularity" not in time_value:
            raise _invalid("query.time requires range or granularity")
        if "range" in time_value:
            validated_time["range"] = _validate_range_shape(time_value["range"])
        if "granularity" in time_value:
            granularity = _require_string(
                time_value["granularity"], "query.time.granularity"
            )
            if granularity not in _GRANULARITIES:
                raise _invalid("query.time.granularity is unsupported")
            validated_time["granularity"] = granularity
        validated["time"] = validated_time
    if "order_by" in query:
        order_by = query["order_by"]
        if not isinstance(order_by, list) or len(order_by) > 3:
            raise _invalid("query.order_by must contain between 0 and 3 items")
        validated_order = [
            _validate_order_shape(item, index) for index, item in enumerate(order_by)
        ]
        order_members = [item["member"] for item in validated_order]
        if len(set(order_members)) != len(order_members):
            raise _invalid("query.order_by must not contain duplicate members")
        validated["order_by"] = validated_order
    if "limit" in query:
        limit = query["limit"]
        if type(limit) is not int or not 1 <= limit <= max_limit:
            raise _invalid(f"query.limit must be an integer between 1 and {max_limit}")
        validated["limit"] = limit
    return {"status": "matched", "query": validated}


def validate_metric_query_shape(raw: object, max_limit: int = 500) -> dict:
    """Validate exact JSON structure without coercing model output."""

    root = _require_exact_dict(
        raw,
        allowed={"status", "reason", "query"},
        required={"status"},
        field="model output",
    )
    status = root["status"]
    if status == "unmatched":
        if set(root) != {"status", "reason"}:
            raise _invalid("unmatched output must contain exactly status and reason")
        reason = _require_string(root["reason"], "reason")
        if reason not in _SEMANTIC_MISS_REASONS:
            raise _invalid("unmatched reason is unsupported")
        return {"status": "unmatched", "reason": reason}
    if status == "matched":
        return _validate_matched_shape(root, max_limit)
    raise _invalid("status must be matched or unmatched")


def _catalog_member(name: str, member_catalog: Mapping[str, CubeMember]) -> CubeMember:
    try:
        return member_catalog[name]
    except KeyError as exc:
        raise MetricQueryValidationError(
            "unknown_member", f"Unknown Cube member: {name}"
        ) from exc


def _validate_members(
    query: dict,
    measure_candidates: Collection[str],
    member_catalog: Mapping[str, CubeMember],
) -> None:
    candidate_names = set(measure_candidates)
    measures = query["measures"]
    dimensions = query.get("dimensions", [])
    filters = query.get("filters", [])
    time_value = query.get("time")
    order_by = query.get("order_by", [])

    referenced = [*measures, *dimensions]
    referenced.extend(item["member"] for item in filters)
    referenced.extend(item["member"] for item in order_by)
    if time_value is not None:
        referenced.append(time_value["dimension"])
    members = {name: _catalog_member(name, member_catalog) for name in referenced}

    for name in measures:
        if members[name].member_type != "measure" or name not in candidate_names:
            raise _invalid(f"Measure {name} is not an eligible candidate")
    for name in dimensions:
        if members[name].member_type != "dimension":
            raise _invalid(f"Dimension {name} is not a dimension member")
    if time_value is not None:
        time_name = time_value["dimension"]
        if members[time_name].member_type != "time_dimension":
            raise _invalid(f"Time dimension {time_name} has the wrong member type")
    for filter_value in filters:
        member = members[filter_value["member"]]
        if member.member_type != "dimension" or not member.filterable:
            raise _invalid(f"Filter member {member.name} is not filterable")
        allowed_operators = {
            "string": _STRING_OPERATORS,
            "number": _NUMERIC_OPERATORS,
        }.get(member.data_type)
        if (
            allowed_operators is None
            or filter_value["operator"] not in allowed_operators
        ):
            raise _invalid(
                f"Operator {filter_value['operator']} is invalid for {member.data_type}"
            )
        if "values" in filter_value and any(
            type(value) not in _FILTER_VALUE_TYPES[member.data_type]
            for value in filter_value["values"]
        ):
            raise _invalid(f"Filter values do not match {member.data_type}")
    selected = {*measures, *dimensions}
    for order in order_by:
        if order["member"] not in selected:
            raise _invalid(f"Order member {order['member']} is not selected")


def _to_metric_query(query: dict) -> MetricQuery:
    filters = tuple(
        MetricFilter(
            member=item["member"],
            operator=cast(FilterOperator, item["operator"]),
            values=tuple(item["values"]) if "values" in item else None,
        )
        for item in query.get("filters", [])
    )
    order_by = tuple(
        MetricOrder(member=item["member"], direction=item["direction"])
        for item in query.get("order_by", [])
    )
    raw_time = query.get("time")
    metric_time = None
    if raw_time is not None:
        raw_range = raw_time.get("range")
        time_range = None
        if raw_range is not None:
            time_range = (
                PresetTimeRange(value=raw_range["value"])
                if raw_range["type"] == "preset"
                else AbsoluteTimeRange(start=raw_range["start"], end=raw_range["end"])
            )
        metric_time = MetricTime(
            dimension=raw_time["dimension"],
            range=time_range,
            granularity=raw_time.get("granularity"),
        )
    return MetricQuery(
        measures=tuple(query["measures"]),
        dimensions=tuple(query.get("dimensions", [])),
        filters=filters,
        time=metric_time,
        order_by=order_by,
        limit=query.get("limit"),
    )


def _today_in_shanghai() -> date:
    return datetime.now(_SHANGHAI_TIMEZONE).date()


def validate_metric_query_result(
    raw: object,
    measure_candidates: Collection[str],
    member_catalog: Mapping[str, CubeMember],
    max_limit: int,
    today: date | None = None,
) -> MetricQueryDecision:
    """Validate a model decision and produce a ready-to-send Cube query."""

    validated = validate_metric_query_shape(raw, max_limit=max_limit)
    if validated["status"] == "unmatched":
        return MetricQueryDecision(
            status="unmatched",
            reason=cast(SemanticMissReason, validated["reason"]),
            query=None,
            cube_query=None,
        )
    query_value = validated["query"]
    _validate_members(query_value, measure_candidates, member_catalog)
    query = _to_metric_query(query_value)
    cube_query = to_cube_query(query, member_catalog, today or _today_in_shanghai())
    return MetricQueryDecision(
        status="matched",
        reason=None,
        query=query,
        cube_query=cube_query,
    )


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def resolve_time_range(value: object, today: date) -> tuple[str, str]:
    """Resolve a validated range into inclusive ISO calendar boundaries."""

    time_range = _validate_range_shape(value)
    if time_range["type"] == "absolute":
        return time_range["start"], time_range["end"]

    preset = time_range["value"]
    if preset == "today":
        start = end = today
    elif preset == "yesterday":
        start = end = today - timedelta(days=1)
    elif preset == "this_week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif preset == "last_week":
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
    elif preset == "this_month":
        start = date(today.year, today.month, 1)
        end = _month_end(today.year, today.month)
    elif preset == "last_month":
        end = date(today.year, today.month, 1) - timedelta(days=1)
        start = date(end.year, end.month, 1)
    elif preset in {"this_quarter", "last_quarter"}:
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, quarter_month, 1)
        if preset == "last_quarter":
            end = start - timedelta(days=1)
            start = date(end.year, ((end.month - 1) // 3) * 3 + 1, 1)
        else:
            end_month = quarter_month + 2
            end = _month_end(today.year, end_month)
    elif preset == "this_year":
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
    elif preset == "last_year":
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
    else:
        days = {"last_7_days": 7, "last_30_days": 30, "last_90_days": 90}[preset]
        start = today - timedelta(days=days - 1)
        end = today
    return start.isoformat(), end.isoformat()


def to_cube_query(
    query: MetricQuery,
    member_catalog: Mapping[str, CubeMember],
    today: date | None = None,
) -> dict:
    """Convert validated IR to the deterministic Cube REST query shape."""

    today = today or _today_in_shanghai()

    referenced = [*query.measures, *query.dimensions]
    referenced.extend(filter_value.member for filter_value in query.filters)
    referenced.extend(order.member for order in query.order_by)
    if query.time is not None:
        referenced.append(query.time.dimension)
    for name in referenced:
        _catalog_member(name, member_catalog)

    cube_query: dict = {"measures": list(query.measures)}
    if query.dimensions:
        cube_query["dimensions"] = list(query.dimensions)
    if query.filters:
        cube_filters = []
        for filter_value in query.filters:
            cube_filter = {
                "member": filter_value.member,
                "operator": _CUBE_OPERATORS[filter_value.operator],
            }
            if filter_value.values is not None:
                cube_filter["values"] = list(
                    cast(tuple[FilterValue, ...], filter_value.values)
                )
            cube_filters.append(cube_filter)
        cube_query["filters"] = cube_filters
    if query.time is not None:
        time_dimension = {
            "dimension": query.time.dimension,
        }
        if query.time.range is not None:
            raw_range: dict
            if isinstance(query.time.range, PresetTimeRange):
                raw_range = {"type": "preset", "value": query.time.range.value}
            else:
                raw_range = {
                    "type": "absolute",
                    "start": query.time.range.start,
                    "end": query.time.range.end,
                }
            start, end = resolve_time_range(raw_range, today)
            time_dimension["dateRange"] = [start, end]
        if query.time.granularity is not None:
            time_dimension["granularity"] = cast(
                TimeGranularity, query.time.granularity
            )
        cube_query["timeDimensions"] = [time_dimension]
    if query.order_by:
        cube_query["order"] = {
            order.member: order.direction for order in query.order_by
        }
    cube_query["limit"] = query.limit if query.limit is not None else 100
    cube_query["timezone"] = "Asia/Shanghai"
    return cube_query


def normalize_cube_result(response: object) -> list[dict]:
    """Extract rows from Cube 1.7.46's single-query top-level data array."""

    if not isinstance(response, dict):
        raise QueryExecutionError(
            "cube_unavailable", "Cube response must be an object", True
        )
    data = response.get("data")
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise QueryExecutionError(
            "cube_unavailable", "Cube response data is invalid", True
        )
    return list(data)
