/**
 * 查询过程模块
 * 独立展示查询级状态，避免查询状态展开影响分析过程面板
 */
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { cn, formatTime } from "../lib/format";
import type { ChatMessage, ProcessEvent, QueryMode } from "../types/agent";

type QueryProcessPanelProps = {
    processEvents?: ProcessEvent[];
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

function getQuerySummaryState(
    status: ChatMessage["status"] | undefined,
    hasResult: boolean,
    queryMode: QueryMode | undefined,
    verified: boolean,
) : ProcessSummaryState {
    if (status === "cancelled") return { tone: "terminal", text: "查询已停止" };
    if (status === "error") {
        return { tone: "error", text: "查询失败" };
    }
    if (status === "streaming") return { tone: "running", text: "查询进行中" };
    if (status === "done") return { tone: "terminal", text: "查询完成" };
    if (hasResult) {
        return { tone: "terminal", text: verified ? "结果已验证" : "结果未验证" };
    }
    if (queryMode) {
        return {
            tone: "terminal",
            text:
                queryMode === "metric"
                    ? "治理指标查询"
                    : queryMode === "graph"
                      ? "业务关系查询"
                      : "智能 SQL 查询",
        };
    }
    return { tone: "terminal", text: "查询已创建" };
}

export function QueryProcessPanel({
    processEvents = [],
    queryMode,
    status,
    hasResult = false,
    verified = false,
    errorCode,
}: QueryProcessPanelProps) {
    const [open, setOpen] = useState(false);
    const summaryState = getQuerySummaryState(status, hasResult, queryMode, verified);
    const hasProcessState =
        processEvents.length > 0 ||
        Boolean(queryMode) ||
        hasResult ||
        Boolean(status) ||
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
                        {processEvents.length > 0 && (
                            <div>
                                <div className="font-serif text-sm font-bold text-ink">节点明细</div>
                                <ol className="mt-2 space-y-2">
                                    {processEvents.map((event, index) => (
                                        <li
                                            key={`${event.step}-${event.occurredAt}-${index}`}
                                            className="grid min-w-[620px] grid-cols-[minmax(140px,0.35fr)_minmax(280px,1fr)_auto] items-baseline gap-3 text-xs leading-5"
                                        >
                                            <span className="font-mono text-indigo">{event.step}</span>
                                            <span className="text-ink/75">{eventLabel(event)}</span>
                                            <time
                                                dateTime={new Date(event.occurredAt).toISOString()}
                                                className="text-ink/45"
                                            >
                                                {formatTime(event.occurredAt)}
                                            </time>
                                        </li>
                                    ))}
                                </ol>
                            </div>
                        )}

                        <div className="grid gap-2 text-xs leading-5 text-ink/65 sm:grid-cols-3">
                            <div>
                                <div className="font-semibold text-ink/75">查询状态</div>
                                <div>{summaryState.text}</div>
                            </div>
                            <div>
                                <div className="font-semibold text-ink/75">查询方式</div>
                                <div>
                                    {queryMode === "metric"
                                        ? "治理指标"
                                        : queryMode === "graph"
                                          ? "业务知识图谱"
                                          : queryMode === "sql"
                                            ? "智能 SQL"
                                            : "待确定"}
                                </div>
                            </div>
                            <div>
                                <div className="font-semibold text-ink/75">结果状态</div>
                                <div>
                                    {hasResult ? (verified ? "已验证" : "未验证") : "尚未返回"}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
