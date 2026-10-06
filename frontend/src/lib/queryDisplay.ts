const ROUTE_REASON_LABELS: Record<string, string> = {
    governed_measure_matched: "已匹配治理指标",
    no_measure_candidate: "未匹配到可用业务指标",
    missing_dimension_mapping: "统计维度未匹配到已接入范围",
    unsupported_analysis: "当前分析方式暂不支持",
    ambiguous_measure: "指标口径需要补充",
};

export function routeReasonLabel(reason?: string): string | undefined {
    if (!reason) return undefined;
    return ROUTE_REASON_LABELS[reason] ?? "查询范围需要调整";
}
