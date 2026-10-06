/**
 * 前端应用主组件
 * 负责聊天会话状态、SSE 事件消费和整体页面布局（「数字账房」工作台）
 */
import {
    Eraser,
    MessageCircle,
    MessageSquarePlus,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { logout } from "./auth/keycloak";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { HistoryPage } from "./components/HistoryPage";
import { KnowledgeGraphPage } from "./components/KnowledgeGraphPage";
import { MessageBubble } from "./components/MessageBubble";
import { MobileSessionDrawer } from "./components/MobileSessionDrawer";
import { SemanticModelPage } from "./components/SemanticModelPage";
import { SessionList } from "./components/SessionList";
import { UserAvatarMenu, type UserAvatarMenuHandle } from "./components/UserAvatarMenu";
import { UserManagementPanel } from "./components/UserManagementPanel";
import {
    archiveQuerySession,
    createQuerySession,
    deleteQuerySession,
    getQuerySession,
    getCurrentUserCapability,
    listQuerySessions,
    searchQuerySessions,
    streamQueryWithReplay,
    updateQuerySessionTitle,
    type QuerySessionSummary,
} from "./lib/agentApi";
import { cn, summarizeResult } from "./lib/format";
import { sanitizeMetricItems } from "./lib/metricDisplay";
import { hydrateSessionMessages } from "./lib/sessionHydration";
import {
    isAgentManagementPath,
    semanticBuildPath,
    semanticBuildTabForPath,
} from "./lib/semanticModel";
import { capabilityPresentation, shouldAutoScrollChat } from "./lib/userManagement";
import type { AgentEvent, ChatMessage, ProcessEvent, StepState } from "./types/agent";

const examples = [
    "统计 2025 年第一季度各大区的 GMV，并按 GMV 从高到低排序",
    "统计 2025 年 3 月各商品品类的销量和销售额",
    "查询华东地区 2025 年第一季度销售额最高的前 5 个商品",
    "按会员等级统计 2025 年第一季度的订单数和销售额",
];

function makeId() {
    return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function upsertStep(steps: StepState[] = [], event: Extract<AgentEvent, { type: "progress" }>) {
    const next = steps.filter((item) => item.step !== event.step);
    next.push({
        step: event.step,
        status: event.status,
        message: event.message,
        updatedAt: Date.now(),
    });
    return next;
}

function appendProcessEvent(
    processEvents: ProcessEvent[] = [],
    event: Extract<AgentEvent, { type: "progress" }>,
) {
    return [
        ...processEvents,
        {
            step: event.step,
            status: event.status,
            message: event.message ?? null,
            occurredAt: Date.now(),
        },
    ];
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

type AppPath =
    | "/"
    | "/history"
    | "/user-management"
    | "/knowledge-graph"
    | "/agent-management/metrics"
    | "/agent-management/dimensions"
    | "/agent-management/cubes";

function readAppPath(): AppPath {
    if (window.location.pathname === "/history") return "/history";
    if (window.location.pathname === "/user-management") return "/user-management";
    if (window.location.pathname === "/knowledge-graph") return "/knowledge-graph";
    if (window.location.pathname === "/semantic-model") {
        window.history.replaceState({}, "", "/agent-management/metrics");
        return "/agent-management/metrics";
    }
    if (window.location.pathname === "/agent-management/metrics") {
        return "/agent-management/metrics";
    }
    if (window.location.pathname === "/agent-management/dimensions") {
        return "/agent-management/dimensions";
    }
    if (window.location.pathname === "/agent-management/cubes") {
        return "/agent-management/cubes";
    }
    return "/";
}

export default function App({ username }: AppProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [path, setPath] = useState<AppPath>(readAppPath);
    const [sessions, setSessions] = useState<QuerySessionSummary[]>([]);
    const [hasMoreSessions, setHasMoreSessions] = useState(false);
    const [sessionsLoading, setSessionsLoading] = useState(true);
    const [sessionsError, setSessionsError] = useState<string | null>(null);
    const [sessionDetailError, setSessionDetailError] = useState<string | null>(null);
    const [navigationError, setNavigationError] = useState<string | null>(null);
    const [mobileSessionError, setMobileSessionError] = useState<string | null>(null);
    const [loadingSessionId, setLoadingSessionId] = useState<string | null>(null);
    const [draft, setDraft] = useState("");
    const [activeController, setActiveController] = useState<AbortController | null>(null);
    const [canManageUsers, setCanManageUsers] = useState<boolean | null>(null);
    const [canManageSemanticModel, setCanManageSemanticModel] = useState<boolean | null>(null);
    const [capabilityError, setCapabilityError] = useState<unknown>(null);
    const [mobileSessionsOpen, setMobileSessionsOpen] = useState(false);
    const [semanticModelDirty, setSemanticModelDirty] = useState(false);
    const scrollRef = useRef<HTMLDivElement | null>(null);
    const desktopNewSessionRef = useRef<HTMLButtonElement | null>(null);
    const userMenuRef = useRef<UserAvatarMenuHandle | null>(null);
    const mobileUserMenuRef = useRef<UserAvatarMenuHandle | null>(null);
    const desktopLogoutRef = {
        current: { focus: () => userMenuRef.current?.focusTrigger() },
    };
    const mobileSessionTriggerRef = useRef<HTMLButtonElement | null>(null);
    const initialSessionLoadedRef = useRef(false);
    const capabilityLoadedRef = useRef(false);
    const sessionsRefreshGenerationRef = useRef(0);

    const isStreaming = Boolean(activeController);
    const canSubmit = draft.trim().length > 0 && !isStreaming;
    const managementCapability = capabilityPresentation(canManageUsers, capabilityError);
    const semanticModelCapability = canManageSemanticModel === true;

    const closeMobileSessions = () => {
        setMobileSessionsOpen(false);
        requestAnimationFrame(() => {
            mobileSessionTriggerRef.current?.focus();
        });
    };

    const navigateTo = (nextPath: AppPath) => {
        if (nextPath === path) return;
        if (isStreaming) {
            setNavigationError("查询进行中，请先停止查询后再切换页面。");
            return;
        }
        const leavingAgentManagement =
            isAgentManagementPath(path) && !isAgentManagementPath(nextPath);
        if (semanticModelDirty && leavingAgentManagement) {
            if (!window.confirm("当前 Agent 管理草稿尚未保存，确定离开吗？")) return;
            setSemanticModelDirty(false);
        }
        setNavigationError(null);
        window.history.pushState({}, "", nextPath);
        setPath(nextPath);
    };

    useEffect(() => {
        const handlePopState = () => {
            const nextPath = readAppPath();
            if (isStreaming) {
                window.history.pushState({}, "", path);
                setNavigationError("查询进行中，请先停止查询后再切换页面。");
                return;
            }
            const leavingAgentManagement =
                isAgentManagementPath(path) && !isAgentManagementPath(nextPath);
            if (semanticModelDirty && leavingAgentManagement) {
                window.history.pushState({}, "", path);
                setNavigationError("当前 Agent 管理草稿尚未保存，请先保存或确认离开。");
                return;
            }
            setNavigationError(null);
            setPath(nextPath);
        };
        window.addEventListener("popstate", handlePopState);
        return () => window.removeEventListener("popstate", handlePopState);
    }, [isStreaming, path, semanticModelDirty]);

    useEffect(() => {
        const desktopMediaQuery = window.matchMedia("(min-width: 1024px)");
        const closeMobileSessionsOnDesktop = () => {
            if (desktopMediaQuery.matches && mobileSessionsOpen) {
                setMobileSessionsOpen(false);
                requestAnimationFrame(() => {
                    if (!desktopNewSessionRef.current?.disabled) {
                        desktopNewSessionRef.current?.focus();
                        return;
                    }
                    desktopLogoutRef.current?.focus();
                });
            }
        };

        closeMobileSessionsOnDesktop();
        desktopMediaQuery.addEventListener("change", closeMobileSessionsOnDesktop);
        window.addEventListener("resize", closeMobileSessionsOnDesktop);

        return () => {
            desktopMediaQuery.removeEventListener("change", closeMobileSessionsOnDesktop);
            window.removeEventListener("resize", closeMobileSessionsOnDesktop);
        };
    }, [mobileSessionsOpen]);

    useEffect(() => {
        if (capabilityLoadedRef.current) return;
        capabilityLoadedRef.current = true;
        void getCurrentUserCapability()
            .then((response) => {
                setCanManageUsers(response.can_manage_users);
                setCanManageSemanticModel(response.can_manage_semantic_model);
            })
            .catch((error: unknown) => setCapabilityError(error));
    }, []);

    useEffect(() => {
        if (!shouldAutoScrollChat(path !== "/")) return;
        scrollRef.current?.scrollTo({
            top: scrollRef.current.scrollHeight,
            behavior: "smooth",
        });
    }, [messages, path]);

    const openSession = async (targetSessionId: string) => {
        if (isStreaming || loadingSessionId !== null) return false;
        const openedFromMobile = mobileSessionsOpen;
        setMobileSessionsOpen(false);
        setMobileSessionError(null);
        setLoadingSessionId(targetSessionId);
        setSessionsError(null);
        setSessionDetailError(null);
        try {
            const detail = await getQuerySession(targetSessionId, 200, 0);
            setMessages(hydrateSessionMessages(detail));
            setSessionId(detail.session.session_id);
            setDraft("");
            return true;
        } catch (error) {
            const message = error instanceof Error ? error.message : "会话详情加载失败";
            setSessionDetailError(message);
            if (openedFromMobile) setMobileSessionError(message);
            return false;
        } finally {
            setLoadingSessionId(null);
        }
    };

    const refreshSessions = async (openLatest = false) => {
        const generation = ++sessionsRefreshGenerationRef.current;
        setSessionsLoading(true);
        setSessionsError(null);
        try {
            const nextSessions = await listQuerySessions(10, 0);
            if (generation !== sessionsRefreshGenerationRef.current) return;
            setSessions(nextSessions);
            let historyError: string | null = null;
            try {
                const page = await searchQuerySessions("", 1, 10);
                if (generation !== sessionsRefreshGenerationRef.current) return;
                setHasMoreSessions(page.total > 10);
            } catch (error) {
                if (generation !== sessionsRefreshGenerationRef.current) return;
                setHasMoreSessions(false);
                historyError = error instanceof Error ? error.message : "历史对话加载失败";
            }
            if (generation !== sessionsRefreshGenerationRef.current) return;
            if (openLatest && !sessionId && nextSessions[0]) {
                await openSession(nextSessions[0].session_id);
            }
            if (generation === sessionsRefreshGenerationRef.current && historyError) {
                setSessionsError(historyError);
            }
        } catch (error) {
            if (generation !== sessionsRefreshGenerationRef.current) return;
            setHasMoreSessions(false);
            setSessionsError(error instanceof Error ? error.message : "会话列表加载失败");
        } finally {
            if (generation === sessionsRefreshGenerationRef.current) {
                setSessionsLoading(false);
            }
        }
    };

    useEffect(() => {
        if (initialSessionLoadedRef.current) return;
        initialSessionLoadedRef.current = true;
        void refreshSessions(false);
    }, []);

    const updateSessionSummary = (updated: QuerySessionSummary) => {
        setSessions((current) =>
            current.map((session) =>
                session.session_id === updated.session_id ? updated : session,
            ),
        );
    };

    const renameSession = async (session: QuerySessionSummary) => {
        const title = window.prompt("会话标题", session.title)?.trim();
        if (!title || title === session.title) return;
        try {
            const updated = await updateQuerySessionTitle(session.session_id, title);
            updateSessionSummary(updated);
            await refreshSessions(false);
        } catch (error) {
            setSessionsError(error instanceof Error ? error.message : "会话重命名失败");
            throw error;
        }
    };

    const archiveSession = async (session: QuerySessionSummary) => {
        if (!window.confirm(`归档“${session.title}”？`)) return;
        try {
            await archiveQuerySession(session.session_id);
            setSessions((current) =>
                current.filter((item) => item.session_id !== session.session_id),
            );
            if (session.session_id === sessionId) {
                setMessages([]);
                setSessionId(null);
            }
            await refreshSessions(false);
        } catch (error) {
            setSessionsError(error instanceof Error ? error.message : "会话归档失败");
            throw error;
        }
    };

    const removeSession = async (session: QuerySessionSummary) => {
        if (!window.confirm(`删除“${session.title}”？`)) return;
        try {
            await deleteQuerySession(session.session_id);
            setSessions((current) =>
                current.filter((item) => item.session_id !== session.session_id),
            );
            if (session.session_id === sessionId) {
                setMessages([]);
                setSessionId(null);
            }
            await refreshSessions(false);
        } catch (error) {
            setSessionsError(error instanceof Error ? error.message : "会话删除失败");
            throw error;
        }
    };

    const openSessionFromHistory = async (targetSessionId: string) => {
        const opened = await openSession(targetSessionId);
        if (opened) {
            navigateTo("/");
        }
    };

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
        let replayAttempted = false;
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
                                    event.message ??
                                    (event.status === "running"
                                        ? `正在执行：${event.step}`
                                        : message.content),
                                steps: upsertStep(message.steps, event),
                                processEvents: appendProcessEvent(message.processEvents, event),
                            };
                        case "metrics":
                            return {
                                ...message,
                                metrics: sanitizeMetricItems(event.data),
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
                                rowCount: event.row_count,
                                truncated: event.truncated,
                                exportId: event.export_id,
                            };
                        case "error":
                            return {
                                ...message,
                                status: "error",
                                content:
                                    event.code === "conversation_clarification_required"
                                        ? event.message
                                        : "这次查询没有成功。",
                                error: event.message,
                                errorCode: event.code,
                                retryable: event.retryable,
                                suggestions: event.suggestions,
                                missingRequirements: event.missing_requirements,
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
            let currentSessionId = sessionId;
            if (!currentSessionId) {
                const session = await createQuerySession(query);
                currentSessionId = session.session_id;
                setSessionId(currentSessionId);
            }
            await streamQueryWithReplay(query, {
                signal: controller.signal,
                onEvent,
                sessionId: currentSessionId,
                onReplayAttempt: () => {
                    replayAttempted = true;
                },
            });
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
                              content: isAbort
                                  ? "已停止本次查询。"
                                  : replayAttempted
                                    ? "查询连接已中断，无法恢复本次查询。"
                                    : "无法连接问数接口。",
                              error: isAbort
                                  ? undefined
                                  : replayAttempted
                                    ? "请重新发起查询。"
                                    : error instanceof Error
                                      ? error.message
                                      : String(error),
                              errorCode: replayAttempted ? "sse_replay_failed" : undefined,
                              retryable: replayAttempted ? true : undefined,
                          }
                        : message,
                ),
            );
        } finally {
            setActiveController(null);
            void refreshSessions(false);
        }
    };

    const stopQuery = () => {
        activeController?.abort();
    };

    const clearConversation = () => {
        if (isStreaming) return;
        setMobileSessionsOpen(false);
        setMobileSessionError(null);
        setMessages([]);
        setDraft("");
        setSessionId(null);
    };

    const handleLogout = async () => {
        activeController?.abort();
        try {
            await logout();
        } catch {
            window.location.reload();
        }
    };

    const pageTitle =
        path === "/user-management"
            ? "用户管理"
            : path === "/knowledge-graph"
              ? "知识图谱"
            : path === "/history"
              ? "历史对话"
              : isAgentManagementPath(path)
                ? "Agent 管理"
                : "问数工作台";
    const pageSubtitle =
        path === "/user-management"
            ? "管理应用角色、账号状态和有效权限摘要"
            : path === "/knowledge-graph"
              ? "商品经营、客户行为与区域关系"
            : path === "/history"
              ? "检索、恢复和维护历史问数会话"
              : isAgentManagementPath(path)
                ? "统一维护可被问数智能体调用的指标与维度"
                : "自然语言直连数仓";
    const isAgentManagementPage = isAgentManagementPath(path);
    const isUserManagementPage = path === "/user-management";
    const isKnowledgeGraphPage = path === "/knowledge-graph";
    const isAdminPage = isUserManagementPage || isAgentManagementPage || isKnowledgeGraphPage;

    return (
        <div className="h-dvh overflow-hidden bg-paper text-ink">
            <div
                className={cn(
                    "relative grid h-full min-h-0 overflow-hidden",
                    isAdminPage
                        ? "lg:grid-cols-1"
                        : "lg:grid-cols-[300px_minmax(0,1fr)]",
                )}
            >
                {!isAdminPage && (
                <aside inert={mobileSessionsOpen} className="hidden min-h-0 border-r border-ink/10 bg-paper text-ink lg:flex lg:flex-col">
                    <div className="border-b border-ink/10 px-5 py-5">
                        <div className="flex items-center gap-3">
                            <Seal className="h-10 w-10 text-xl" />
                            <div>
                                <div className="font-serif text-lg font-bold leading-6">慧答</div>
                            </div>
                        </div>
                    </div>

                        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
                                    <button
                                        ref={desktopNewSessionRef}
                                        type="button"
                                        onClick={clearConversation}
                                        disabled={isStreaming}
                                        className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-cinnabar text-sm font-semibold text-paper transition hover:bg-[#0B6178] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/60 focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:bg-cinnabar/40"
                                    >
                                        <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
                                        新会话
                                    </button>

                                    <div className="mt-6">
                                        <SessionList
                                            sessions={sessions}
                                            selectedSessionId={sessionId}
                                            loading={sessionsLoading || loadingSessionId !== null}
                                            loadingSessionId={loadingSessionId}
                                            disabled={isStreaming}
                                            error={sessionsError}
                                            onSelect={(targetSessionId) => void openSession(targetSessionId)}
                                            onRename={renameSession}
                                            onArchive={archiveSession}
                                            onDelete={removeSession}
                                            showHistoryLink={hasMoreSessions}
                                            onOpenHistory={() => navigateTo("/history")}
                                        />
                                    </div>
                        </div>
                        <div className="shrink-0 border-t border-ink/10 px-4 py-4">
                            <div className="flex items-center gap-3">
                                <UserAvatarMenu
                                    ref={userMenuRef}
                                    username={username}
                                    showManagement={managementCapability.showEntry}
                                    onOpenManagement={() => navigateTo("/user-management")}
                                    showGovernance={semanticModelCapability}
                                    onOpenGovernance={() => navigateTo("/agent-management/metrics")}
                                    showKnowledgeGraph={semanticModelCapability}
                                    onOpenKnowledgeGraph={() => navigateTo("/knowledge-graph")}
                                    onLogout={() => void handleLogout()}
                                    menuPlacement="above"
                                />
                                <div className="min-w-0">
                                    <p className="truncate text-sm font-semibold text-ink" title={username}>
                                        {username}
                                    </p>
                                    <p className="text-xs text-ink/45">当前账号</p>
                                </div>
                            </div>
                        </div>

                </aside>
                )}

                <main className="relative flex min-h-0 min-w-0 flex-col overflow-hidden">
                    {!isAgentManagementPage && !isKnowledgeGraphPage && <header inert={mobileSessionsOpen} className="flex h-16 shrink-0 items-center justify-between border-b border-ink/10 bg-paper px-4 lg:px-6">
                        <div className="flex min-w-0 items-center gap-3">
                            <Seal className="h-9 w-9 text-lg lg:hidden" />
                            <div className="min-w-0">
                                <div className="truncate font-serif text-base font-bold text-ink">
                                    {path === "/" ? (
                                        <>
                                            <span className="lg:hidden">慧答</span>
                                            <span className="hidden lg:inline">{pageTitle}</span>
                                        </>
                                    ) : pageTitle}
                                </div>
                                <div className="truncate text-xs text-ink/45">{pageSubtitle}</div>
                            </div>
                        </div>
                        <div className="flex items-center gap-1 sm:gap-3">
                            <button
                                ref={mobileSessionTriggerRef}
                                type="button"
                                onClick={() => setMobileSessionsOpen(true)}
                                aria-label="会话"
                                aria-expanded={mobileSessionsOpen}
                                title="会话"
                                className="grid h-11 w-11 place-items-center rounded-full text-ink/70 hover:bg-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50 lg:hidden"
                            >
                                <MessageCircle className="h-4 w-4" aria-hidden="true" />
                            </button>
                            <span
                                className="hidden max-w-20 truncate text-xs text-ink/60 sm:block sm:max-w-40 lg:hidden"
                                title={username}
                            >
                                {username}
                            </span>
                            {path === "/" && (
                                <button
                                    type="button"
                                    onClick={clearConversation}
                                    disabled={messages.length === 0 || isStreaming}
                                    className="grid h-9 w-9 place-items-center rounded-full text-ink/55 transition hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40 disabled:cursor-not-allowed disabled:opacity-35 lg:hidden"
                                    title="清空"
                                    aria-label="清空"
                                >
                                    <Eraser className="h-4 w-4" aria-hidden="true" />
                                </button>
                            )}
                            <UserAvatarMenu
                                ref={mobileUserMenuRef}
                                username={username}
                                showManagement={managementCapability.showEntry}
                                onOpenManagement={() => navigateTo("/user-management")}
                                showGovernance={semanticModelCapability}
                                onOpenGovernance={() => navigateTo("/agent-management/metrics")}
                                showKnowledgeGraph={semanticModelCapability}
                                onOpenKnowledgeGraph={() => navigateTo("/knowledge-graph")}
                                onLogout={() => void handleLogout()}
                                menuPlacement="below"
                                className="lg:hidden"
                            />
                        </div>
                    </header>}

                    {managementCapability.hint && path === "/" && (
                        <p role="status" aria-live="polite" className="border-b border-ink/10 bg-paper px-4 py-2 text-sm text-oxide">
                            {managementCapability.hint} 聊天仍可继续使用。
                        </p>
                    )}

                    {navigationError && (
                        <p role="status" aria-live="polite" className="border-b border-ink/10 bg-paper px-4 py-2 text-sm text-oxide">
                            {navigationError}
                        </p>
                    )}

                    {mobileSessionError && (
                        <p role="alert" aria-live="assertive" className="border-b border-ink/10 bg-paper px-4 py-2 text-sm text-oxide lg:hidden">
                            {mobileSessionError}
                        </p>
                    )}

                    {path === "/history" ? (
                        <HistoryPage
                            selectedSessionId={sessionId}
                            onBack={() => navigateTo("/")}
                            onOpenSession={openSessionFromHistory}
                            onRename={renameSession}
                            onArchive={archiveSession}
                            onDelete={removeSession}
                            disabled={isStreaming}
                            loadingSessionId={loadingSessionId}
                            externalError={sessionDetailError}
                            onClearExternalError={() => setSessionDetailError(null)}
                        />
                        ) : path === "/user-management" ? (
                            canManageUsers === null && capabilityError === null ? (
                                <div className="grid min-h-0 flex-1 place-items-center bg-canvas px-6 text-center"><p className="text-sm text-ink/60">正在读取用户管理权限…</p></div>
                            ) : managementCapability.showEntry ? (
                                <UserManagementPanel onBack={() => navigateTo("/")} />
                            ) : (
                                <div className="grid min-h-0 flex-1 place-items-center bg-canvas px-6 text-center"><div><p className="font-serif text-xl font-bold text-ink">没有用户管理权限</p><p className="mt-2 text-sm text-ink/55">请联系平台管理员申请用户管理权限。</p></div></div>
                            )
                        ) : path === "/knowledge-graph" ? (
                            <KnowledgeGraphPage onBack={() => navigateTo("/")} />
                        ) : isAgentManagementPath(path) ? (
                        semanticModelCapability ? (
                            <SemanticModelPage
                                onBack={() => navigateTo("/")}
                                onDirtyChange={setSemanticModelDirty}
                                initialTab={semanticBuildTabForPath(path)}
                                onTabChange={(tab) => navigateTo(semanticBuildPath(tab))}
                            />
                        ) : (
                            <div className="grid min-h-0 flex-1 place-items-center bg-canvas px-6 text-center"><div><p className="font-serif text-xl font-bold text-ink">没有 Agent 管理权限</p><p className="mt-2 text-sm text-ink/55">请联系平台管理员申请语义模型操作权限。</p></div></div>
                        )
                    ) : (
                        <>
                            <div inert={mobileSessionsOpen} ref={scrollRef} className="workbench-mist min-h-0 flex-1 overflow-y-auto overscroll-contain">
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

                            <div inert={mobileSessionsOpen} className="shrink-0">
                                <Composer
                                    value={draft}
                                    disabled={!canSubmit}
                                    isStreaming={isStreaming}
                                    onChange={setDraft}
                                    onSubmit={() => startQuery()}
                                    onStop={stopQuery}
                                />
                            </div>
                        </>
                    )}
                    {mobileSessionsOpen && (
                        <MobileSessionDrawer
                            sessions={sessions}
                            selectedSessionId={sessionId}
                            loading={sessionsLoading || loadingSessionId !== null}
                            loadingSessionId={loadingSessionId}
                            disabled={isStreaming}
                            error={sessionsError}
                            onNewSession={clearConversation}
                            onSelect={(targetSessionId) => void openSession(targetSessionId)}
                            onRename={renameSession}
                            onArchive={archiveSession}
                            onDelete={removeSession}
                            showHistoryLink={hasMoreSessions}
                            onOpenHistory={() => navigateTo("/history")}
                            onClose={closeMobileSessions}
                        />
                    )}
                </main>
            </div>
        </div>
    );
}
