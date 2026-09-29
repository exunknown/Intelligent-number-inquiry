/**
 * 前端应用主组件
 * 负责聊天会话状态、SSE 事件消费和整体页面布局（「数字账房」工作台）
 */
import {
    Eraser,
    ListChecks,
    LogOut,
    MessageSquarePlus,
    ScrollText,
    Server,
    UserRound,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { logout } from "./auth/keycloak";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { MessageBubble } from "./components/MessageBubble";
import { streamQuery } from "./lib/agentApi";
import { cn, summarizeResult } from "./lib/format";
import type { AgentEvent, ChatMessage, StepState } from "./types/agent";

const examples = [
    "统计 2025 年第一季度各大区的 GMV，并按 GMV 从高到低排序",
    "统计 2025 年 3 月各商品品类的销量和销售额",
    "查询华东地区 2025 年第一季度销售额最高的前 5 个商品",
    "按会员等级统计 2025 年第一季度的订单数和销售额",
];

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "Vite /api proxy";

function makeId() {
    return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function upsertStep(steps: StepState[] = [], event: Extract<AgentEvent, { type: "progress" }>) {
    const next = steps.filter((item) => item.step !== event.step);
    next.push({
        step: event.step,
        status: event.status,
        updatedAt: Date.now(),
    });
    return next;
}

function assertNever(value: never): never {
    throw new Error(`未处理的智能体事件：${JSON.stringify(value)}`);
}

/** 青瓷印章字标：侧栏、移动端顶栏共用，字号由父级 text-* 控制 */
function Seal({ className }: { className?: string }) {
    return (
        <div
            className={cn(
                "grid shrink-0 place-items-center bg-indigo/15 text-indigo",
                className,
            )}
        >
            <span className="font-serif font-bold leading-none">慧</span>
        </div>
    );
}

type AppProps = {
    username: string;
};

export default function App({ username }: AppProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [draft, setDraft] = useState("");
    const [activeController, setActiveController] = useState<AbortController | null>(null);
    const scrollRef = useRef<HTMLDivElement | null>(null);

    const isStreaming = Boolean(activeController);
    const canSubmit = draft.trim().length > 0 && !isStreaming;

    const completedCount = useMemo(
        () => messages.filter((message) => message.role === "assistant" && message.status === "done").length,
        [messages],
    );

    useEffect(() => {
        scrollRef.current?.scrollTo({
            top: scrollRef.current.scrollHeight,
            behavior: "smooth",
        });
    }, [messages]);

    const startQuery = async (rawQuery = draft) => {
        const query = rawQuery.trim();
        if (!query || isStreaming) return;

        const userMessage: ChatMessage = {
            id: makeId(),
            role: "user",
            content: query,
            createdAt: Date.now(),
        };

        const assistantId = makeId();
        const assistantMessage: ChatMessage = {
            id: assistantId,
            role: "assistant",
            content: "正在连接问数智能体...",
            createdAt: Date.now(),
            status: "streaming",
            steps: [],
        };

        const controller = new AbortController();
        setActiveController(controller);
        setDraft("");
        setMessages((current) => [...current, userMessage, assistantMessage]);

        const onEvent = (event: AgentEvent) => {
            setMessages((current) =>
                current.map((message) => {
                    if (message.id !== assistantId) return message;

                    switch (event.type) {
                        case "progress":
                            return {
                                ...message,
                                content:
                                    event.status === "running"
                                        ? `正在执行：${event.step}`
                                        : message.content,
                                steps: upsertStep(message.steps, event),
                            };
                        case "metrics":
                            return {
                                ...message,
                                metrics: event.data,
                            };
                        case "route":
                            return {
                                ...message,
                                queryMode: event.mode,
                                routeReason: event.reason,
                            };
                        case "result":
                            return {
                                ...message,
                                status: "done",
                                content: summarizeResult(event.data),
                                queryMode: event.source,
                                result: event.data,
                                verified: event.verified,
                                warning: event.warning,
                            };
                        case "error":
                            return {
                                ...message,
                                status: "error",
                                content: "这次查询没有成功。",
                                error: event.message,
                                errorCode: event.code,
                                retryable: event.retryable,
                            };
                        case "heartbeat":
                            return message;
                        default:
                            return assertNever(event);
                    }
                }),
            );
        };

        try {
            await streamQuery(query, { signal: controller.signal, onEvent });
            setMessages((current) =>
                current.map((message) =>
                    message.id === assistantId && message.status === "streaming"
                        ? { ...message, status: "done", content: "流程已结束，后端未返回查询结果。" }
                        : message,
                ),
            );
        } catch (error) {
            const isAbort = error instanceof DOMException && error.name === "AbortError";
            setMessages((current) =>
                current.map((message) =>
                    message.id === assistantId
                        ? {
                              ...message,
                              status: isAbort ? "done" : "error",
                              content: isAbort ? "已停止本次查询。" : "无法连接问数接口。",
                              error: isAbort ? undefined : error instanceof Error ? error.message : String(error),
                          }
                        : message,
                ),
            );
        } finally {
            setActiveController(null);
        }
    };

    const stopQuery = () => {
        activeController?.abort();
    };

    const clearConversation = () => {
        if (isStreaming) return;
        setMessages([]);
        setDraft("");
    };

    const handleLogout = async () => {
        activeController?.abort();
        try {
            await logout();
        } catch {
            window.location.reload();
        }
    };

    return (
        <div className="h-dvh overflow-hidden bg-paper text-ink">
            <div className="relative grid h-full min-h-0 overflow-hidden lg:grid-cols-[300px_minmax(0,1fr)]">
                <aside className="hidden min-h-0 border-r border-ink/10 bg-paper text-ink lg:flex lg:flex-col">
                    <div className="border-b border-ink/10 px-5 py-5">
                        <div className="flex items-center gap-3">
                            <Seal className="h-10 w-10 text-xl" />
                            <div>
                                <div className="font-serif text-lg font-bold leading-6">慧答</div>
                                <div className="text-xs text-ink/45">shopkeeper-agent</div>
                            </div>
                        </div>
                    </div>

                    <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-4">
                        <button
                            type="button"
                            onClick={clearConversation}
                            disabled={isStreaming}
                            className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-cinnabar text-sm font-semibold text-paper transition hover:bg-[#ad3a26] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/60 focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:bg-cinnabar/40"
                        >
                            <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
                            新会话
                        </button>

                        <section>
                            <div className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold text-ink/45">
                                <ScrollText className="h-3.5 w-3.5" aria-hidden="true" />
                                示例问题
                            </div>
                            <div className="space-y-2">
                                {examples.map((example) => (
                                    <button
                                        key={example}
                                        type="button"
                                        disabled={isStreaming}
                                        onClick={() => startQuery(example)}
                                        className="w-full rounded-lg border border-ink/15 bg-white px-3 py-3 text-left text-sm leading-5 text-ink/80 shadow-line transition hover:-translate-y-0.5 hover:border-cinnabar/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                        {example}
                                    </button>
                                ))}
                            </div>
                        </section>
                    </div>

                    <div className="border-t border-ink/10 p-4">
                        <div className="grid gap-2 text-xs text-ink/55">
                            <div className="flex items-center justify-between gap-3">
                                <span className="inline-flex items-center gap-2">
                                    <Server className="h-3.5 w-3.5" aria-hidden="true" />
                                    接口
                                </span>
                                <span className="truncate font-mono">{API_BASE_URL}</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <span className="inline-flex items-center gap-2">
                                    <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
                                    已完成
                                </span>
                                <span className="tabular-nums">{completedCount}</span>
                            </div>
                            <div className="flex items-center justify-between gap-3">
                                <span className="inline-flex items-center gap-2">
                                    <UserRound className="h-3.5 w-3.5" aria-hidden="true" />
                                    用户
                                </span>
                                <span className="truncate" title={username}>
                                    {username}
                                </span>
                            </div>
                        </div>
                    </div>
                </aside>

                <main className="flex min-h-0 min-w-0 flex-col overflow-hidden">
                    <header className="flex h-16 shrink-0 items-center justify-between border-b border-ink/10 bg-paper px-4 lg:px-6">
                        <div className="flex min-w-0 items-center gap-3">
                            <Seal className="h-9 w-9 text-lg lg:hidden" />
                            <div className="min-w-0">
                                <div className="truncate font-serif text-base font-bold text-ink">
                                    <span className="lg:hidden">慧答</span>
                                    <span className="hidden lg:inline">问数工作台</span>
                                </div>
                                <div className="truncate text-xs text-ink/45">自然语言直连数仓</div>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            <span
                                className="max-w-20 truncate text-xs text-ink/60 sm:max-w-40"
                                title={username}
                            >
                                {username}
                            </span>
                            <span className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-white px-3 py-1.5 text-xs text-ink/60">
                                <span
                                    className={cn(
                                        "h-2 w-2 rounded-full",
                                        isStreaming ? "animate-pulse bg-cinnabar" : "bg-pine",
                                    )}
                                />
                                <span className="hidden sm:inline">{isStreaming ? "正在算账" : "就绪"}</span>
                            </span>
                            <button
                                type="button"
                                onClick={clearConversation}
                                disabled={messages.length === 0 || isStreaming}
                                className="grid h-9 w-9 place-items-center rounded-full text-ink/55 transition hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40 disabled:cursor-not-allowed disabled:opacity-35"
                                title="清空"
                                aria-label="清空"
                            >
                                <Eraser className="h-4 w-4" aria-hidden="true" />
                            </button>
                            <button
                                type="button"
                                onClick={() => void handleLogout()}
                                className="grid h-11 w-11 place-items-center rounded-full text-ink/55 transition hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                                title="退出登录"
                                aria-label="退出登录"
                            >
                                <LogOut className="h-4 w-4" aria-hidden="true" />
                            </button>
                        </div>
                    </header>

                    <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[#dfe0d8]">
                        {messages.length === 0 ? (
                            <EmptyState examples={examples} onUseExample={(example) => setDraft(example)} />
                        ) : (
                            <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-6 lg:px-8">
                                {messages.map((message) => (
                                    <MessageBubble key={message.id} message={message} />
                                ))}
                            </div>
                        )}
                    </div>

                    <Composer
                        value={draft}
                        disabled={!canSubmit}
                        isStreaming={isStreaming}
                        onChange={setDraft}
                        onSubmit={() => startQuery()}
                        onStop={stopQuery}
                    />
                </main>
            </div>
        </div>
    );
}
