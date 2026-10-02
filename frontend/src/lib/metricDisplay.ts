import type { MetricDisplayEntry, MetricItem } from "../types/agent";

export function metricLabel(metric: MetricItem): string {
    return typeof metric === "string" ? metric : metric.title || metric.member_id;
}

export function metricDisplayEntries(metrics: MetricItem[] = []): MetricDisplayEntry[] {
    return metrics.filter(
        (metric): metric is MetricDisplayEntry => typeof metric !== "string",
    );
}

export function attachedMetricEntries(metrics: MetricItem[] = []): MetricDisplayEntry[] {
    return metricDisplayEntries(metrics).filter((metric) => metric.role === "attached");
}

export function visibleMetricColumns(
    columns: string[],
    metrics: MetricItem[] = [],
    hiddenAttachedMetricIds: ReadonlySet<string> = new Set(),
): string[] {
    const metricByColumn = new Map<string, MetricDisplayEntry>();
    for (const metric of metricDisplayEntries(metrics)) {
        metricByColumn.set(metric.member_id, metric);
        metricByColumn.set(metric.title, metric);
    }

    return columns.filter((column) => {
        const metric = metricByColumn.get(column);
        return (
            !metric ||
            metric.role !== "attached" ||
            !hiddenAttachedMetricIds.has(metric.member_id)
        );
    });
}
