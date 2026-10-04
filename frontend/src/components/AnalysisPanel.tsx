/**
 * 分析过程模块
 * 包裹执行流程与指标信息，展示一次问数的完整分析过程，默认折叠
 * （靛青边条「批注」样式，附在助手气泡上方；展开后内部小节用分隔线分区，不再套卡片）
 */
import { ChevronDown, Route } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { StepRail } from "./StepRail";
import { cn } from "../lib/format";
import { attachedMetricEntries, metricDisplayEntries, metricLabel } from "../lib/metricDisplay";
import type { ChatMessage, MetricItem, QueryMode, StepState } from "../types/agent";

type AnalysisPanelProps = {
    steps?: StepState[];
    metrics?: MetricItem[];
    queryMode?: QueryMode;
    routeReason?: string;
    status?: ChatMessage["status"];
    hasResult?: boolean;
    verified?: boolean;
    errorCode?: string;
    hiddenAttachedMetricIds?: ReadonlySet<string>;
    onToggleAttachedMetric?: (memberId: string, visible: boolean) => void;
    onToggleAllAttachedMetrics?: (visible: boolean) => void;
};

export function AnalysisPanel({
    steps = [],
    metrics,
    queryMode,
    routeReason,
    status,
    hasResult = false,
    verified = false,
    errorCode,
    hiddenAttachedMetricIds = new Set(),
    onToggleAttachedMetric,
    onToggleAllAttachedMetrics,
}: AnalysisPanelProps) {
    const [open, setOpen] = useState(false);

    const runningStep = steps.find((item) => item.status === "running")?.step ?? null;
    const doneCount = steps.filter((item) => item.status === "success").length;
    const attachedMetrics = attachedMetricEntries(metrics);
    const summaryMetrics = metrics?.map(metricLabel) ?? [];
    const allAttachedVisible = attachedMetrics.every(
        (metric) => !hiddenAttachedMetricIds.has(metric.member_id),
    );
    const isPartiallyVisible =
        attachedMetrics.some((metric) => !hiddenAttachedMetricIds.has(metric.member_id)) &&
        !allAttachedVisible;
    const allAttachedCheckboxRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (allAttachedCheckboxRef.current) {
            allAttachedCheckboxRef.current.indeterminate = isPartiallyVisible;
        }
    }, [isPartiallyVisible]);

    if (steps.length === 0 && !queryMode && !hasResult && status !== "error" && !errorCode) {
        return null;
    }

    const summary = runningStep
        ? `正在执行：${runningStep}`
        : summaryMetrics.length > 0
          ? `查询指标：${summaryMetrics.join("，")}`
          : `已执行 ${doneCount} 步`;

    const toggle = () => {
        setOpen((current) => !current);
    };

    return (
        <section className="mb-4 overflow-hidden rounded-xl border border-ink/15 border-l-2 border-l-indigo bg-white/80 shadow-line">
            <button
                type="button"
                onClick={toggle}
                aria-expanded={open}
                className="flex w-full items-center gap-2.5 px-4 py-3 text-left transition hover:bg-white/60"
            >
                <span className="shrink-0 font-serif text-sm font-bold text-ink">分析过程</span>
                <span
                    className={cn(
                        "min-w-0 flex-1 truncate text-xs",
                        runningStep ? "text-cinnabar" : "text-ink/45",
                    )}
                >
                    {summary}
                </span>
                <ChevronDown
                    className={cn(
                        "h-4 w-4 shrink-0 text-ink/40 transition-transform duration-300",
                        open && "rotate-180",
                    )}
                    aria-hidden="true"
                />
            </button>

            <div
                className={cn(
                    "grid transition-all duration-300 ease-out",
                    open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
                )}
            >
                <div className="min-h-0 overflow-hidden">
                    <div className="space-y-4 border-t border-ink/10 px-4 py-4">
                        {queryMode && (
                            <div className="flex min-w-0 items-center gap-2 text-xs leading-5 text-ink/60">
                                <Route className="h-3.5 w-3.5 shrink-0 text-indigo" aria-hidden="true" />
                                <span className="shrink-0 font-semibold text-ink/75">查询路由</span>
                                <span className="shrink-0 whitespace-nowrap font-mono text-indigo">
                                    {queryMode === "metric" ? "治理指标" : "智能 SQL"}
                                </span>
                                {routeReason && (
                                    <span className="min-w-0 truncate text-ink/45" title={routeReason}>
                                        {routeReason}
                                    </span>
                                )}
                            </div>
                        )}

                        <StepRail
                            steps={steps}
                            queryMode={queryMode}
                            status={status}
                            hasResult={hasResult}
                            verified={verified}
                            errorCode={errorCode}
                        />

                        <div className="border-t border-ink/10 pt-3">
                            <div className="font-serif text-sm font-bold text-ink">指标信息</div>
                            <p className="mt-1.5 text-sm leading-6 text-ink/70">
                                查询指标：
                                {summaryMetrics.length > 0 ? summaryMetrics.join("，") : "暂无"}
                            </p>
                            {metricDisplayEntries(metrics).some((metric) => Boolean(metric.compatibility_note)) && (
                                <div className="mt-2 space-y-1 text-xs leading-5 text-ink/55">
                                    <div className="font-semibold text-ink/70">口径说明</div>
                                    {metricDisplayEntries(metrics)
                                        .filter((metric) => Boolean(metric.compatibility_note))
                                        .map((metric) => (
                                            <div key={metric.member_id}>
                                                {metric.title}：{metric.compatibility_note}
                                            </div>
                                        ))}
                                </div>
                            )}
                            {attachedMetrics.length > 0 && (
                                <div className="mt-3 space-y-2 border-t border-ink/10 pt-3">
                                    <label className="flex items-center gap-2 text-xs font-semibold text-ink/75">
                                        <input
                                            ref={allAttachedCheckboxRef}
                                            type="checkbox"
                                            checked={allAttachedVisible}
                                            aria-checked={
                                                isPartiallyVisible
                                                    ? "mixed"
                                                    : allAttachedVisible
                                                      ? "true"
                                                      : "false"
                                            }
                                            onChange={(event) =>
                                                onToggleAllAttachedMetrics?.(event.target.checked)
                                            }
                                            className="h-4 w-4 accent-indigo"
                                        />
                                        显示附带指标
                                    </label>
                                    <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                                        {attachedMetrics.map((metric) => {
                                            const visible = !hiddenAttachedMetricIds.has(metric.member_id);
                                            return (
                                                <label
                                                    key={metric.member_id}
                                                    className="flex min-w-0 items-center gap-2 text-xs text-ink/65"
                                                >
                                                    <input
                                                        type="checkbox"
                                                        checked={visible}
                                                        onChange={(event) =>
                                                            onToggleAttachedMetric?.(
                                                                metric.member_id,
                                                                event.target.checked,
                                                            )
                                                        }
                                                        className="h-4 w-4 shrink-0 accent-indigo"
                                                    />
                                                    <span className="truncate" title={metricLabel(metric)}>
                                                        {metricLabel(metric)}
                                                    </span>
                                                </label>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
