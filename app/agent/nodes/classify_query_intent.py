"""问数问题意图分类节点。

该节点只负责选择召回方向，不负责指标权限判断，也不授权任何执行引擎。
"""

from typing import Literal

from langgraph.runtime import Runtime

from app.agent.context import DataAgentContext
from app.agent.state import DataAgentState
from app.core.log import logger

QueryIntent = Literal["metric", "relation", "hybrid", "detail"]

_RELATION_TERMS = (
    "偏好",
    "喜欢",
    "适合",
    "关联",
    "一起购买",
    "搭配",
    "属于",
    "依赖",
    "来源",
    "来自",
    "影响",
    "关系",
    "推荐",
    "相关",
)
_METRIC_TERMS = (
    "销售额",
    "成交额",
    "成交金额",
    "gmv",
    "订单数",
    "订单量",
    "数量",
    "销量",
    "客单价",
    "aov",
    "金额",
    "收入",
    "同比",
    "环比",
    "趋势",
    "排名",
    "占比",
    "平均",
)
_DETAIL_TERMS = (
    "明细",
    "清单",
    "列表",
    "原始记录",
    "具体订单",
    "订单明细",
)


def _contains_any(query: str, terms: tuple[str, ...]) -> list[str]:
    normalized = query.casefold()
    return [term for term in terms if term.casefold() in normalized]


def classify_query(query: str) -> tuple[QueryIntent, float, dict[str, object]]:
    """使用可解释规则分类，低置信度时不把问题强行当成指标查询。"""

    relation_terms = _contains_any(query, _RELATION_TERMS)
    metric_terms = _contains_any(query, _METRIC_TERMS)
    detail_terms = _contains_any(query, _DETAIL_TERMS)

    if detail_terms:
        intent: QueryIntent = "detail"
        confidence = 0.9
    elif relation_terms and metric_terms:
        intent = "hybrid"
        confidence = 0.9
    elif relation_terms:
        intent = "relation"
        confidence = 0.85
    elif metric_terms:
        intent = "metric"
        confidence = 0.8
    else:
        intent = "detail"
        confidence = 0.4

    requires_graph = intent in {"relation", "hybrid"}
    requires_metric = intent in {"metric", "hybrid"}
    preferred_engine = {
        "metric": "cube",
        "relation": "graph",
        "hybrid": "cube",
        "detail": "sql",
    }[intent]
    plan = {
        "intent": intent,
        "confidence": confidence,
        "requires_graph": requires_graph,
        "requires_metric": requires_metric,
        "preferred_engine": preferred_engine,
        "matched_relation_terms": relation_terms,
        "matched_metric_terms": metric_terms,
        "matched_detail_terms": detail_terms,
    }
    return intent, confidence, plan


async def classify_query_intent(
    state: DataAgentState, runtime: Runtime[DataAgentContext]
) -> dict[str, object]:
    """为后续召回节点生成可解释的查询计划。"""

    writer = runtime.stream_writer
    step = "识别查询意图"
    writer({"type": "progress", "step": step, "status": "running"})
    try:
        intent, confidence, plan = classify_query(state.get("query", ""))
        logger.info(
            "查询意图识别成功 intent={} confidence={} requires_graph={}",
            intent,
            confidence,
            plan["requires_graph"],
        )
        writer({"type": "progress", "step": step, "status": "success"})
        return {
            "query_intent": intent,
            "query_intent_confidence": confidence,
            "query_plan": plan,
        }
    except Exception as error:
        logger.error("{} failed error_type={}", step, type(error).__name__)
        writer({"type": "progress", "step": step, "status": "error"})
        raise
