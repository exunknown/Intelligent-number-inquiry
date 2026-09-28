/**
 * 聊天消息气泡组件
 * 用户黛蓝块 / 助手白卡，组合回复、结果表格；分析过程作为气泡上方的独立模块
 */
import { BadgeCheck, Bot, Check, Copy, TriangleAlert, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AnalysisPanel } from "./AnalysisPanel";
import { ResultTable } from "./ResultTable";
import { cn, formatTime, toClipboardText } from "../lib/format";
import type { ChatMessage } from "../types/agent";

export function MessageBubble({ message }: { message: ChatMessage }) {
    const isUser = message.role === "user";
    const [copied, setCopied] = useState(false);
    const copyTimerRef = useRef<number | null>(null);

    useEffect(
        () => () => {
            if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
        },
        [],
    );

    const copy = async () => {
        const text =
            message.result !== undefined ? toClipboardText(message.result) : message.content;
        await navigator.clipboard.writeText(text);
        setCopied(true);
        if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
        copyTimerRef.current = window.setTimeout(() => setCopied(false), 1600);
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
                    />
                )}

                <div
                    className={cn(
                        "relative rounded-2xl border px-5 py-4 shadow-line",
                        isUser
                            ? "border-dai bg-dai text-paper"
                            : "border-ink/20 bg-white text-ink",
                    )}
                >
                    <div className="flex items-start justify-between gap-3">
                        <p className="whitespace-pre-wrap text-[15px] leading-7">
                            {message.content}
                            {message.status === "streaming" && (
                                <span className="ml-1 inline-block h-4 w-[7px] animate-pulse bg-cinnabar align-[-2px]" />
                            )}
                        </p>
                        {!isUser && message.status !== "streaming" && (
                            <button
                                type="button"
                                onClick={copy}
                                className={cn(
                                    "shrink-0 rounded-full p-1.5 outline-none transition focus:opacity-100 focus:ring-2 focus:ring-cinnabar/40",
                                    copied
                                        ? "text-pine opacity-100"
                                        : "text-ink/45 opacity-0 hover:bg-ink/5 hover:text-ink group-hover:opacity-100",
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

                    {message.error && (
                        <div className="mt-3 rounded-lg border border-oxide/30 bg-oxide/10 px-3 py-2 text-sm text-oxide">
                            {message.error}
                            {message.retryable && message.errorCode?.startsWith("cube_") && (
                                <span className="ml-2 whitespace-nowrap font-semibold">可重试</span>
                            )}
                        </div>
                    )}

                    {!isUser && message.result !== undefined && (
                        <>
                            {message.verified === true && (
                                <div className="mt-4 inline-flex max-w-full items-center gap-1.5 text-xs font-medium text-pine">
                                    <BadgeCheck className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                                    <span>已按指标平台口径执行</span>
                                </div>
                            )}
                            {message.verified === false && (
                                <div className="mt-4 flex items-start gap-2 rounded-lg border border-oxide/30 bg-oxide/10 px-3 py-2 text-sm leading-6 text-oxide">
                                    <TriangleAlert
                                        className="mt-1 h-4 w-4 shrink-0"
                                        aria-hidden="true"
                                    />
                                    <span>
                                        {message.warning ??
                                            "该结果由智能 SQL 生成，未经业务口径验证，请人工核对。"}
                                    </span>
                                </div>
                            )}
                            <ResultTable data={message.result} />
                        </>
                    )}

                    <div
                        className={cn(
                            "mt-3 text-xs",
                            isUser ? "text-paper/50" : "text-ink/45",
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
