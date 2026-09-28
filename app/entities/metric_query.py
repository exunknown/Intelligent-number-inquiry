"""Metric Query IR transport types and validated immutable values."""

from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict

SemanticMissReason = Literal[
    "no_measure_candidate",
    "missing_dimension_mapping",
    "unsupported_analysis",
    "ambiguous_measure",
]

FilterOperator = Literal[
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
]

TimeGranularity = Literal["day", "week", "month", "quarter", "year"]
FilterValue = str | int | float


class PresetTimeRangeInput(TypedDict):
    type: Literal["preset"]
    value: str


class AbsoluteTimeRangeInput(TypedDict):
    type: Literal["absolute"]
    start: str
    end: str


class MetricFilterInput(TypedDict):
    member: str
    operator: FilterOperator
    values: NotRequired[list[FilterValue]]


class MetricOrderInput(TypedDict):
    member: str
    direction: Literal["asc", "desc"]


class MetricTimeInput(TypedDict):
    dimension: str
    range: NotRequired[PresetTimeRangeInput | AbsoluteTimeRangeInput]
    granularity: NotRequired[TimeGranularity]


class MetricQueryInput(TypedDict):
    measures: list[str]
    dimensions: NotRequired[list[str]]
    filters: NotRequired[list[MetricFilterInput]]
    time: NotRequired[MetricTimeInput]
    order_by: NotRequired[list[MetricOrderInput]]
    limit: NotRequired[int]


class MatchedMetricQueryInput(TypedDict):
    status: Literal["matched"]
    query: MetricQueryInput


class UnmatchedMetricQueryInput(TypedDict):
    status: Literal["unmatched"]
    reason: SemanticMissReason


@dataclass(frozen=True)
class PresetTimeRange:
    value: str


@dataclass(frozen=True)
class AbsoluteTimeRange:
    start: str
    end: str


@dataclass(frozen=True)
class MetricFilter:
    member: str
    operator: FilterOperator
    values: tuple[FilterValue, ...] | None


@dataclass(frozen=True)
class MetricOrder:
    member: str
    direction: Literal["asc", "desc"]


@dataclass(frozen=True)
class MetricTime:
    dimension: str
    range: PresetTimeRange | AbsoluteTimeRange | None
    granularity: TimeGranularity | None


@dataclass(frozen=True)
class MetricQuery:
    measures: tuple[str, ...]
    dimensions: tuple[str, ...]
    filters: tuple[MetricFilter, ...]
    time: MetricTime | None
    order_by: tuple[MetricOrder, ...]
    limit: int | None


@dataclass(frozen=True)
class MetricQueryDecision:
    status: Literal["matched", "unmatched"]
    reason: SemanticMissReason | None
    query: MetricQuery | None
    cube_query: dict | None


class MetricQueryValidationError(ValueError):
    """A model-output error with a stable machine-readable classification."""

    def __init__(
        self,
        code: Literal["invalid_model_output", "unknown_member"],
        message: str,
    ):
        super().__init__(message)
        self.code = code
