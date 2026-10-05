/**
 * 查询过程模块
 * 独立展示实时过程事件和执行流程，避免过程展开状态影响指标分析面板
 */
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { cn, formatTime } from "../lib/format";
import type { ChatMessage, ProcessEvent, QueryMode, StepState } from "../types/agent";
import { StepRail } from "./StepRail";

type QueryProcessPanelProps = {
    processEvents?: ProcessEvent[];
    steps?: StepState[];
    queryMode?: QueryMode;
    status?: ChatMessage["status"];
    hasResult?: boolean;
    verified?: boolean;
    errorCode?: string;
};

function eventLabel(event: ProcessEvent) {
    return event.message ??
        (event.status === "running"
            ? `正在执行：${event.step}`
            : event.status === "error"
              ? `执行失败：${event.step}`
              : `已完成：${event.step}`);
}

function processSummary(
    events: ProcessEvent[],
    steps: StepState[],
    status: ChatMessage["status"] | undefined,
) {
    const running = events.find((event) => event.status === "running") ??
        steps.find((step) => step.status === "running");
    if (running) return `正在执行：${running.message ?? running.step}`;
    if (status === "cancelled") return "查询已停止";
    if (status === "error" || events.some((event) => event.status === "error")) {
        return "查询失败";
    }
    if (status === "done") return `查询完成，共 ${events.length || steps.length} 步`;
    return `已执行 ${events.length || steps.length} 步`;
}

export function QueryProcessPanel({
    processEvents = [],
    steps = [],
    queryMode,
    status,
    hasResult = false,
    verified = false,
    errorCode,
}: QueryProcessPanelProps) {
    const [open, setOpen] = useState(false);
    const hasProcessState =
        processEvents.length > 0 ||
        steps.length > 0 ||
        Boolean(queryMode) ||
        hasResult ||
        status === "done" ||
        status === "error" ||
        status === "cancelled" ||
        Boolean(errorCode);

    if (!hasProcessState) return null;

    return (
        <section className="mb-4 overflow-hidden rounded-xl border border-ink/15 border-l-2 border-l-indigo bg-white/80 shadow-line">
            <button
                type="button"
                onClick={() => setOpen((current) => !current)}
                aria-expanded={open}
                className="flex w-full items-center gap-2.5 px-4 py-3 text-left transition hover:bg-white/60"
            >
                <span className="shrink-0 font-serif text-sm font-bold text-ink">查询过程</span>
                <span
                    className={cn(
                        "min-w-0 flex-1 truncate text-xs",
                        status === "error" ||
                            steps.some((step) => step.status === "error") ||
                            processEvents.some((event) => event.status === "error")
                            ? "text-oxide"
                            : steps.some((step) => step.status === "running") ||
                                processEvents.some((event) => event.status === "running")
                              ? "text-cinnabar"
                              : "text-ink/45",
                    )}
                >
                    {processSummary(processEvents, steps, status)}
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
                        <div className="overflow-x-auto">
                            <StepRail
                                steps={steps}
                                queryMode={queryMode}
                                status={status}
                                hasResult={hasResult}
                                verified={verified}
                                errorCode={errorCode}
                            />
                        </div>

                        {processEvents.length > 0 && (
                            <ol className="space-y-2 border-t border-ink/10 pt-3">
                                {processEvents.map((event, index) => (
                                    <li
                                        key={`${event.step}-${event.occurredAt}-${index}`}
                                        className="grid min-w-[620px] grid-cols-[minmax(140px,0.35fr)_minmax(280px,1fr)_auto] items-baseline gap-3 text-xs leading-5"
                                    >
                                        <span className="font-mono text-indigo">{event.step}</span>
                                        <span className="text-ink/75">{eventLabel(event)}</span>
                                        <time dateTime={new Date(event.occurredAt).toISOString()} className="text-ink/45">
                                            {formatTime(event.occurredAt)}
                                        </time>
                                    </li>
                                ))}
                            </ol>
                        )}
                    </div>
                </div>
            </div>
        </section>
    );
}
