"""将常见中文相对时间表达式解析为确定的日期键范围。"""

import re
from calendar import monthrange
from datetime import date, timedelta

_NUMBER_WORDS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def resolve_date_range(query: str, today: date) -> tuple[int, int] | None:
    """解析可确定的相对时间，返回包含起止日期的 ``yyyyMMdd`` 日期键。"""

    text = query.replace(" ", "")
    if "今天" in text:
        return _date_key(today), _date_key(today)
    if "昨天" in text:
        yesterday = today - timedelta(days=1)
        return _date_key(yesterday), _date_key(yesterday)
    if "本月" in text:
        return _date_key(today.replace(day=1)), _date_key(today)
    if "上月" in text:
        previous = _shift_months(today.replace(day=1), -1)
        return _date_key(previous), _date_key(
            previous.replace(day=monthrange(previous.year, previous.month)[1])
        )
    if "今年" in text:
        return _date_key(today.replace(month=1, day=1)), _date_key(today)
    if "去年" in text:
        start = today.replace(year=today.year - 1, month=1, day=1)
        return _date_key(start), _date_key(start.replace(month=12, day=31))

    match = re.search(r"最近([一二两三四五六七八九十\d]+)个?月", text)
    if match:
        months = _parse_count(match.group(1))
        if months > 0:
            return _date_key(_shift_months(today, -months)), _date_key(today)

    match = re.search(r"最近([一二两三四五六七八九十\d]+)天", text)
    if match:
        days = _parse_count(match.group(1))
        if days > 0:
            return _date_key(today - timedelta(days=days - 1)), _date_key(today)

    return None


def _parse_count(value: str) -> int:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value.startswith("十"):
        return 10 + _NUMBER_WORDS.get(value[1:], 0)
    if value.endswith("十"):
        return _NUMBER_WORDS.get(value[0], 0) * 10
    if len(value) == 2 and value[0] in _NUMBER_WORDS and value[1] in _NUMBER_WORDS:
        return _NUMBER_WORDS[value[0]] * 10 + _NUMBER_WORDS[value[1]]
    return _NUMBER_WORDS.get(value, 0)


def _shift_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_offset = divmod(month_index, 12)
    month = month_offset + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _date_key(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day
