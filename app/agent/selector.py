"""Pure policy and validation helpers for the conditional schema selector."""

from __future__ import annotations

import json
import math
from typing import Callable, TypedDict


class SelectorValueDecision(TypedDict):
    """A value evidence item bound to its selected column."""

    value_id: str
    column_id: str


class SelectorDecision(TypedDict):
    """Strict JSON contract returned by the schema selector."""

    keep_tables: list[str]
    drop_tables: list[str]
    keep_values: list[SelectorValueDecision]


def serialize_selector_candidates(candidates: object) -> str:
    """Serialize candidates deterministically for token gating and Selector input."""

    return json.dumps(candidates, ensure_ascii=False, sort_keys=True)


def estimate_token_count(
    text: str,
    token_counter: Callable[[str], int] | None = None,
    chars_per_token: float = 2.0,
) -> int:
    """Estimate prompt tokens without requiring a network tokenizer download."""

    if token_counter is not None:
        return token_counter(text)
    if chars_per_token <= 0:
        raise ValueError("chars_per_token must be greater than zero")
    return math.ceil(len(text) / chars_per_token)


def should_use_selector(
    schema_text: str,
    threshold: int,
    token_counter: Callable[[str], int] | None = None,
    chars_per_token: float = 2.0,
) -> tuple[bool, int]:
    """Return whether Schema Prompt size strictly exceeds the configured threshold."""

    if threshold < 0:
        raise ValueError("selector token threshold cannot be negative")
    token_count = estimate_token_count(
        schema_text,
        token_counter=token_counter,
        chars_per_token=chars_per_token,
    )
    return token_count > threshold, token_count


def validate_selector_result(
    result: object,
    candidate_tables: set[str],
    candidate_values: dict[str, str],
    candidate_columns: set[str],
) -> SelectorDecision:
    """Validate and normalize the Selector JSON against retrieved evidence IDs."""

    if not isinstance(result, dict):
        raise ValueError("selector output must be a JSON object")
    expected_keys = {"keep_tables", "drop_tables", "keep_values"}
    if set(result) != expected_keys:
        raise ValueError("selector output contains unexpected or missing keys")

    keep_tables = _validate_string_list(result["keep_tables"], "keep_tables")
    drop_tables = _validate_string_list(result["drop_tables"], "drop_tables")
    if len(set(keep_tables)) != len(keep_tables):
        raise ValueError("keep_tables contains duplicate table IDs")
    if len(set(drop_tables)) != len(drop_tables):
        raise ValueError("drop_tables contains duplicate table IDs")
    if set(keep_tables) & set(drop_tables):
        raise ValueError("a table cannot be both kept and dropped")
    if set(keep_tables) | set(drop_tables) != candidate_tables:
        raise ValueError("selector must classify every candidate table exactly once")
    if not set(keep_tables).issubset(candidate_tables):
        raise ValueError("keep_tables contains an unknown table ID")
    if not set(drop_tables).issubset(candidate_tables):
        raise ValueError("drop_tables contains an unknown table ID")

    raw_values = result["keep_values"]
    if not isinstance(raw_values, list):
        raise ValueError("keep_values must be a JSON array")

    keep_values: list[SelectorValueDecision] = []
    seen_value_ids: set[str] = set()
    for raw_value in raw_values:
        if not isinstance(raw_value, dict) or set(raw_value) != {
            "value_id",
            "column_id",
        }:
            raise ValueError(
                "each keep_values item must contain value_id and column_id"
            )
        value_id = raw_value["value_id"]
        column_id = raw_value["column_id"]
        if not isinstance(value_id, str) or not isinstance(column_id, str):
            raise ValueError("value_id and column_id must be strings")
        if value_id in seen_value_ids:
            raise ValueError("keep_values contains duplicate value IDs")
        if value_id not in candidate_values:
            raise ValueError("keep_values contains an unknown value ID")
        if column_id not in candidate_columns:
            raise ValueError("keep_values contains an unknown column ID")
        if candidate_values[value_id] != column_id:
            raise ValueError("value_id is not associated with the selected column_id")
        seen_value_ids.add(value_id)
        keep_values.append({"value_id": value_id, "column_id": column_id})

    return {
        "keep_tables": keep_tables,
        "drop_tables": drop_tables,
        "keep_values": keep_values,
    }


def _validate_string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be an array of strings")
    return list(value)
