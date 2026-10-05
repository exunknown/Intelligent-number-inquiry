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

type ProcessSummaryTone = "running" | "error" | "terminal";

type ProcessSummaryState = {
    tone: ProcessSummaryTone;
    text: string;
};

function getProcessSummaryState(
    events: ProcessEvent[],
    steps: StepState[],
    status: ChatMessage["status"] | undefined,
) : ProcessSummaryState {
    if (status === "cancelled") return { tone: "terminal", text: "查询已停止" };
    if (status === "error") {
        return { tone: "error", text: "查询失败" };
    }
    const latestEvents = new Map<string, ProcessEvent>();
    for (const event of events) {
        latestEvents.set(event.step, event);
    }
    if (status === "done") {
        return {
            tone: "terminal",
            text: `查询完成，共 ${latestEvents.size || steps.length} 步`,
        };
    }

    const running = [...latestEvents.values()].reverse().find(
        (event) => event.status === "running",
    ) ?? [...steps].reverse().find((step) => step.status === "running");
    if (running) {
        return { tone: "running", text: `正在执行：${running.message ?? running.step}` };
    }
    if (
        [...latestEvents.values()].some((event) => event.status === "error") ||
        steps.some((step) => step.status === "error")
    ) {
        return { tone: "error", text: "查询失败" };
    }
    return { tone: "terminal", text: `已执行 ${latestEvents.size || steps.length} 步` };
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
    const summaryState = getProcessSummaryState(processEvents, steps, status);
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
                        summaryState.tone === "error"
                            ? "text-oxide"
                            : summaryState.tone === "running"
                              ? "text-cinnabar"
                              : "text-ink/45",
                    )}
                >
                    {summaryState.text}
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
