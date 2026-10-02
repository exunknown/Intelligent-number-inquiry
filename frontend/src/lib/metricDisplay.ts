import type { MetricDisplayEntry, MetricItem } from "../types/agent";

export function metricLabel(metric: MetricItem): string {
    return typeof metric === "string" ? metric : metric.title || metric.member_id;
}

export function sanitizeMetricItems(value: unknown): MetricItem[] {
    if (!Array.isArray(value)) return [];
    return value.flatMap((item): MetricItem[] => {
        if (typeof item === "string") return [item];
        if (!item || typeof item !== "object") return [];
        const candidate = item as Record<string, unknown>;
        if (
            typeof candidate.member_id !== "string" ||
            !candidate.member_id ||
            typeof candidate.title !== "string" ||
            !candidate.title
        ) {
            return [];
        }
        const safe: MetricDisplayEntry = {
            member_id: candidate.member_id,
            title: candidate.title,
        };
        if (candidate.role === "primary" || candidate.role === "attached") {
            safe.role = candidate.role;
        }
        if (
            candidate.source_member_id === null ||
            typeof candidate.source_member_id === "string"
        ) {
            safe.source_member_id = candidate.source_member_id;
        }
        return [safe];
    });
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
    const displayMetrics = metricDisplayEntries(metrics);
    const primaryColumns = new Set(
        displayMetrics
            .filter((metric) => metric.role === "primary")
            .flatMap((metric) => [metric.member_id, metric.title]),
    );
    const attachedById = new Map<string, MetricDisplayEntry | null>();
    for (const metric of displayMetrics) {
        if (metric.role !== "attached") continue;
        attachedById.set(
            metric.member_id,
            attachedById.has(metric.member_id) ? null : metric,
        );
    }

    return columns.filter((column) => {
        if (primaryColumns.has(column)) return true;
        const metric = attachedById.get(column);
        return (
            !metric || !hiddenAttachedMetricIds.has(metric.member_id)
        );
    });
}
