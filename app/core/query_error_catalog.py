"""问数错误的安全展示文案。"""

import re
from dataclasses import dataclass, replace

from app.core.query_errors import QueryExecutionError


@dataclass(frozen=True)
class MissingRequirement:
    """面向业务人员说明当前问题还需要补充的信息。"""

    type: str
    label: str
    example: str


@dataclass(frozen=True)
class QueryErrorPresentation:
    """面向调用方展示的稳定错误信息。"""

    code: str
    message: str
    suggestions: tuple[str, ...] = ()
    missing_requirements: tuple[MissingRequirement, ...] = ()


_SQL_POLICY_ERRORS = {
    "invalid_sql": QueryErrorPresentation(
        code="sql_invalid",
        message="查询语句结构有误，请重新描述查询条件。",
    ),
    "multiple_statements": QueryErrorPresentation(
        code="sql_multiple_statements",
        message="一次查询只能包含一条查询语句，请合并或拆分后重试。",
    ),
    "statement_not_read_only": QueryErrorPresentation(
        code="sql_read_only_required",
        message="当前仅支持只读查询，请移除写入、更新或删除操作后重试。",
    ),
    "forbidden_construct": QueryErrorPresentation(
        code="sql_read_only_required",
        message="当前仅支持只读查询，请移除写入、更新或删除操作后重试。",
    ),
    "forbidden_function": QueryErrorPresentation(
        code="sql_unsupported_expression",
        message="查询包含暂不支持的函数或表达式，请改用已支持的指标或维度。",
        suggestions=("改用已支持的指标或维度", "减少自定义函数和复杂表达式"),
    ),
    "query_too_complex": QueryErrorPresentation(
        code="sql_query_too_complex",
        message="查询条件过于复杂，请缩小时间范围或减少查询维度。",
        suggestions=("缩小查询时间范围", "减少同时查询的维度"),
    ),
    "schema_not_allowed": QueryErrorPresentation(
        code="sql_unauthorized_resource",
        message="当前问题涉及的数据源不在已接入范围内，请换用订单、销售额或订单数等已接入业务范围。",
        suggestions=(
            "换用已接入的订单或销售业务范围",
            "联系管理员确认数据源接入状态",
        ),
    ),
    "table_not_supported": QueryErrorPresentation(
        code="sql_unsupported_table",
        message=(
            "当前问题需要的数据范围尚未接入，请换用订单、销售额或订单数等"
            "已接入的业务范围。"
        ),
        suggestions=(
            "补充明确的业务对象和时间范围",
            "换用订单、销售额或订单数等已接入范围",
        ),
        missing_requirements=(
            MissingRequirement(
                type="data_scope",
                label="已接入的数据范围",
                example="订单、销售额或订单数",
            ),
        ),
    ),
    "table_not_allowed": QueryErrorPresentation(
        code="sql_unauthorized_resource",
        message="当前账号无权访问查询所需的数据，请调整查询范围或联系管理员。",
        suggestions=("调整部门或数据范围", "联系管理员确认数据权限"),
    ),
    "column_not_allowed": QueryErrorPresentation(
        code="sql_unauthorized_resource",
        message="当前账号无权访问问题中的部分字段，请减少明细字段或联系管理员申请权限。",
        suggestions=("减少需要展示的明细字段", "联系管理员确认字段权限"),
    ),
    "identifier_unresolved": QueryErrorPresentation(
        code="sql_identifier_unresolved",
        message="当前问题缺少明确的统计对象或展示字段，请补充业务指标、维度或明细字段。",
        suggestions=(
            "补充销售额、订单数等业务指标",
            "补充时间、地区、商品类别或需要展示的字段",
        ),
        missing_requirements=(
            MissingRequirement(
                type="field",
                label="统计对象或展示字段",
                example="销售额、时间、地区或订单金额",
            ),
        ),
    ),
    "wildcard_not_allowed": QueryErrorPresentation(
        code="sql_scope_required",
        message="查询范围过宽，请明确要统计的指标、时间范围和分组维度。",
        suggestions=(
            "明确指定销售额、订单数等指标",
            "补充时间范围和分组维度",
        ),
        missing_requirements=(
            MissingRequirement(
                type="metric",
                label="统计指标",
                example="销售额、订单数或销量",
            ),
            MissingRequirement(
                type="time_range",
                label="统计时间范围",
                example="2025年第一季度",
            ),
            MissingRequirement(
                type="dimension",
                label="分组维度",
                example="按月份、地区或商品类别",
            ),
        ),
    ),
    "no_data_scope": QueryErrorPresentation(
        code="sql_no_data_scope",
        message="当前账号没有可查询的数据范围，请联系管理员配置数据权限。",
        suggestions=("联系管理员配置数据权限",),
    ),
}

_DEFAULT_SQL_POLICY_ERROR = QueryErrorPresentation(
    code="sql_rejected",
    message="查询未通过安全检查，请调整问题后重试。",
)

_RUNTIME_ERRORS = {
    "resource_deadline_exceeded": QueryErrorPresentation(
        code="query_timeout",
        message="查询处理时间超过限制，请缩小时间范围或减少统计维度后重试。",
        suggestions=("缩小查询时间范围", "减少统计维度或明细字段"),
    ),
}

_METRIC_ROUTE_ERRORS = {
    "no_measure_candidate": QueryErrorPresentation(
        code="metric_not_found",
        message="当前问题未匹配到已接入的业务指标，暂时无法完成查询。",
        suggestions=(
            "改用销售额、订单数或销量等已接入指标",
            "使用系统中的业务指标重新提问",
        ),
        missing_requirements=(
            MissingRequirement(
                type="metric",
                label="业务指标",
                example="销售额、订单数或销量",
            ),
        ),
    ),
    "missing_dimension_mapping": QueryErrorPresentation(
        code="metric_dimension_unavailable",
        message=(
            "已识别到业务指标，但当前问题缺少可用的统计维度。"
            "请补充或更换时间、地区或商品类别等维度后重试。"
        ),
        suggestions=(
            "补充或更换时间、地区或商品类别等统计维度",
            "确认当前账号是否有对应维度的数据权限",
        ),
        missing_requirements=(
            MissingRequirement(
                type="dimension",
                label="统计维度",
                example="时间、地区或商品类别",
            ),
        ),
    ),
    "unsupported_analysis": QueryErrorPresentation(
        code="metric_analysis_unsupported",
        message="当前暂不支持这种分析方式，请改用已接入的指标或维度。",
        suggestions=("改用已接入的指标或维度",),
    ),
    "ambiguous_measure": QueryErrorPresentation(
        code="metric_ambiguous",
        message="问题中的指标口径不明确，请补充具体的业务指标。",
        suggestions=("明确说明销售额、订单数或销量等指标",),
        missing_requirements=(
            MissingRequirement(
                type="metric",
                label="明确的业务指标",
                example="销售额、订单数或销量",
            ),
        ),
    ),
}

_SQL_FALLBACK_ERRORS = frozenset(
    {"sql_rejected", "sql_security_not_ready", "forbidden_resource", "no_data_scope"}
)

_TIME_RANGE_PATTERN = re.compile(
    r"\d{4}\s*年|\d{1,2}\s*月|\d{4}[-/]\d{1,2}"
    r"|季度|本月|上月|今年|去年|今天|昨天|本周|上周"
)
_DIMENSION_TERMS = (
    "分组",
    "维度",
    "地区",
    "区域",
    "商品类别",
    "商品品类",
    "品类",
    "商品",
    "客户",
    "省份",
    "城市",
    "部门",
    "月份",
    "日期",
    "会员等级",
    "渠道",
    "订单状态",
)
_METRIC_TERMS = (
    "销售额",
    "订单数",
    "销量",
    "销售量",
    "订单金额",
    "金额总和",
    "总金额",
    "利润率",
    "利润",
    "gmv",
)


def _query_has_dimension(query: str | None) -> bool:
    return bool(query and any(term in query for term in _DIMENSION_TERMS))


def get_sql_policy_error_presentation(reason: str) -> QueryErrorPresentation:
    """按内部拒绝原因返回不泄露 SQL 细节的展示信息。"""

    return _SQL_POLICY_ERRORS.get(reason, _DEFAULT_SQL_POLICY_ERROR)


def _refine_missing_requirements(
    presentation: QueryErrorPresentation, query: str | None
) -> QueryErrorPresentation:
    """移除用户问题中已经明确给出的条件，避免重复提示。"""

    if not presentation.missing_requirements or not query:
        return presentation

    normalized_query = query.casefold()
    has_time_range = _TIME_RANGE_PATTERN.search(query) is not None
    has_dimension = _query_has_dimension(query)
    has_metric = any(term.casefold() in normalized_query for term in _METRIC_TERMS)
    explicit_conditions = {
        "time_range": has_time_range,
        "dimension": has_dimension,
        "metric": has_metric,
    }
    missing_requirements = tuple(
        requirement
        for requirement in presentation.missing_requirements
        if not explicit_conditions.get(requirement.type, False)
    )
    if missing_requirements == presentation.missing_requirements:
        return presentation
    return replace(presentation, missing_requirements=missing_requirements)


def present_query_error(
    error: QueryExecutionError,
    route_reason: str | None = None,
    query: str | None = None,
) -> QueryErrorPresentation:
    """将内部异常转换为可公开给客户端的稳定错误信息。"""

    runtime_error = _RUNTIME_ERRORS.get(error.code)
    if runtime_error is not None:
        presentation = runtime_error
    elif (
        error.code in _SQL_FALLBACK_ERRORS
        and isinstance(route_reason, str)
        and route_reason in _METRIC_ROUTE_ERRORS
    ):
        presentation = _METRIC_ROUTE_ERRORS[route_reason]
        if route_reason == "missing_dimension_mapping" and _query_has_dimension(query):
            presentation = replace(
                presentation,
                message=(
                    "已识别到业务指标，但你指定的统计维度当前未接入或不可用。"
                    "请改用已接入的时间、地区或商品类别等维度后重试。"
                ),
                suggestions=(
                    "改用系统已接入的统计维度",
                    "确认当前账号是否有对应维度的数据权限",
                ),
            )
    elif error.code == "sql_rejected":
        reason = error.details.get("sql_rejection_reason")
        if isinstance(reason, str):
            presentation = get_sql_policy_error_presentation(reason)
        else:
            presentation = QueryErrorPresentation(
                code=error.code, message=error.message
            )
    else:
        presentation = QueryErrorPresentation(code=error.code, message=error.message)
    return _refine_missing_requirements(presentation, query)
