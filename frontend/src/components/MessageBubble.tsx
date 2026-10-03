/**
 * 聊天消息气泡组件
 * 用户黛蓝块 / 助手白卡，组合回复、结果表格；分析过程作为气泡上方的独立模块
 */
import { Bot, Check, Copy, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AnalysisPanel } from "./AnalysisPanel";
import { ResultTable } from "./ResultTable";
import { cn, formatTime, toClipboardText } from "../lib/format";
import { attachedMetricEntries } from "../lib/metricDisplay";
import type { ChatMessage } from "../types/agent";

export function MessageBubble({ message }: { message: ChatMessage }) {
    const isUser = message.role === "user";
    const [copied, setCopied] = useState(false);
    const [hiddenAttachedMetricIds, setHiddenAttachedMetricIds] = useState<Set<string>>(
        new Set(),
    );
    const copyTimerRef = useRef<number | null>(null);

    useEffect(
        () => () => {
            if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
        },
        [],
    );

    useEffect(() => {
        setHiddenAttachedMetricIds(new Set());
    }, [message.id]);

    const copy = async () => {
        const text =
            message.result !== undefined ? toClipboardText(message.result) : message.content;
        await navigator.clipboard.writeText(text);
        setCopied(true);
        if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
        copyTimerRef.current = window.setTimeout(() => setCopied(false), 1600);
    };

    const toggleAttachedMetric = (memberId: string, visible: boolean) => {
        setHiddenAttachedMetricIds((current) => {
            const next = new Set(current);
            if (visible) next.delete(memberId);
            else next.add(memberId);
            return next;
        });
    };

    const toggleAllAttachedMetrics = (visible: boolean) => {
        setHiddenAttachedMetricIds(
            visible
                ? new Set()
                : new Set(attachedMetricEntries(message.metrics).map((metric) => metric.member_id)),
        );
    };

    return (
        <article className={cn("rise-in group flex gap-3", isUser && "justify-end")}>
            {!isUser && (
                <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-dai text-paper">
                    <Bot className="h-4 w-4" aria-hidden="true" />
                </div>
            )}

            <div className={cn("max-w-[920px] flex-1", isUser && "flex max-w-[760px] justify-end")}>
                {!isUser && (
                    <AnalysisPanel
                        steps={message.steps}
                        metrics={message.metrics}
                        queryMode={message.queryMode}
                        routeReason={message.routeReason}
                        hiddenAttachedMetricIds={hiddenAttachedMetricIds}
                        onToggleAttachedMetric={toggleAttachedMetric}
                        onToggleAllAttachedMetrics={toggleAllAttachedMetrics}
                    />
                )}

                <div
                    className={cn(
                        "relative",
                        isUser
                            ? "rounded-2xl border border-dai bg-dai px-5 py-4 text-paper shadow-line"
                            : "px-1 py-0.5 text-ink",
                    )}
                >
                    {!isUser && (
                        <div className="mb-2 flex items-center justify-between gap-3">
                            <div className="text-xs text-ink/45">{formatTime(message.createdAt)}</div>
                            {message.status !== "streaming" && (
                                <button
                                    type="button"
                                    onClick={copy}
                                    className={cn(
                                        "shrink-0 rounded-full p-1.5 outline-none transition focus:opacity-100 focus:ring-2 focus:ring-cinnabar/40",
                                        copied
                                            ? "text-pine opacity-100"
                                            : "text-ink/45 hover:bg-white/70 hover:text-ink",
                                    )}
                                    title={copied ? "已复制" : "复制"}
                                    aria-label={copied ? "已复制" : "复制"}
                                >
                                    {copied ? (
                                        <Check className="h-4 w-4" aria-hidden="true" />
                                    ) : (
                                        <Copy className="h-4 w-4" aria-hidden="true" />
                                    )}
                                </button>
                            )}
                        </div>
                    )}

                    <div className="flex items-start justify-between gap-3">
                        <p className="whitespace-pre-wrap text-[15px] leading-7">
                            {message.content}
                            {message.status === "streaming" && (
                                <span className="ml-1 inline-block h-4 w-[7px] animate-pulse bg-cinnabar align-[-2px]" />
                            )}
                        </p>
                    </div>

                    {message.error && (
                        <div className="mt-4 rounded-xl border border-oxide/25 bg-oxide/5 px-4 py-3 text-sm text-oxide">
                            {message.error}
                            {message.retryable && message.errorCode?.startsWith("cube_") && (
                                <span className="ml-2 whitespace-nowrap font-semibold">可重试</span>
                            )}
                        </div>
                    )}

                    {!isUser && message.result !== undefined && (
                        <ResultTable
                            data={message.result}
                            source={message.queryMode}
                            verified={message.verified}
                            warning={message.warning}
                            exportId={message.exportId}
                            rowCount={message.rowCount}
                            truncated={message.truncated}
                            metrics={message.metrics}
                            hiddenAttachedMetricIds={hiddenAttachedMetricIds}
                        />
                    )}

                    <div
                        className={cn(
                            "mt-3 text-xs",
                            isUser ? "text-paper/50" : "hidden",
                        )}
                    >
                        {formatTime(message.createdAt)}
                    </div>
                </div>
            </div>

            {isUser && (
                <div className="mt-1 grid h-9 w-9 shrink-0 place-items-center rounded-full bg-cinnabar text-paper">
                    <UserRound className="h-4 w-4" aria-hidden="true" />
                </div>
            )}
        </article>
    );
}
