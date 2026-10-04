import {
    Archive,
    Ellipsis,
    LoaderCircle,
    Pencil,
    Trash2,
} from "lucide-react";
import { useState } from "react";
import type { QuerySessionSummary } from "../lib/agentApi";
import { cn } from "../lib/format";

type SessionListProps = {
    sessions: QuerySessionSummary[];
    selectedSessionId: string | null;
    loading: boolean;
    disabled: boolean;
    error: string | null;
    onSelect: (sessionId: string) => void;
    onRename: (session: QuerySessionSummary) => void | Promise<void>;
    onArchive: (session: QuerySessionSummary) => void | Promise<void>;
    onDelete: (session: QuerySessionSummary) => void | Promise<void>;
    heading?: string;
    emptyMessage?: string;
    showHistoryLink?: boolean;
    onOpenHistory?: () => void;
    loadingSessionId?: string | null;
};

export function SessionList({
    sessions,
    selectedSessionId,
    loading,
    disabled,
    error,
    onSelect,
    onRename,
    onArchive,
    onDelete,
    heading = "历史会话",
    emptyMessage = "还没有历史会话",
    showHistoryLink = false,
    onOpenHistory,
    loadingSessionId = null,
}: SessionListProps) {
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);
    const [busySessionId, setBusySessionId] = useState<string | null>(null);

    const runSessionAction = async (
        action: (session: QuerySessionSummary) => void | Promise<void>,
        session: QuerySessionSummary,
    ) => {
        setOpenMenuId(null);
        setBusySessionId(session.session_id);
        try {
            await action(session);
        } finally {
            setBusySessionId(null);
        }
    };

    return (
        <section aria-label="历史会话">
            <div className="mb-2 flex items-center justify-between px-1 text-xs font-medium text-ink/45">
                <span>{heading}</span>
                {loading && (
                    <span role="status" className="inline-flex items-center gap-1.5">
                        <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        <span>加载中</span>
                    </span>
                )}
            </div>

            {error && (
                <div
                    role="alert"
                    className="mb-2 border border-oxide/20 bg-oxide/5 px-3 py-2 text-xs leading-5 text-oxide"
                >
                    {error}
                </div>
            )}

            {!loading && sessions.length === 0 && !error && (
                <div
                    role="status"
                    className="border border-dashed border-ink/15 px-3 py-4 text-center text-xs leading-5 text-ink/45"
                >
                    {emptyMessage}
                </div>
            )}

            <div className="space-y-1.5 rounded-xl bg-canvas/65 p-2">
                {sessions.map((session) => {
                    const selected = session.session_id === selectedSessionId;
                    const menuOpen = session.session_id === openMenuId;
                    const selectionDisabled =
                        disabled || loadingSessionId !== null || busySessionId !== null;
                    return (
                        <div key={session.session_id} className="group relative">
                            <button
                                type="button"
                                disabled={selectionDisabled}
                                aria-busy={loadingSessionId === session.session_id}
                                onClick={() => {
                                    setOpenMenuId(null);
                                    onSelect(session.session_id);
                                }}
                                aria-pressed={selected}
                                className={cn(
                                    "flex min-h-11 w-full min-w-0 items-center rounded-lg px-3 py-2 pr-12 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/45 disabled:cursor-not-allowed disabled:opacity-55",
                                    selected
                                        ? "bg-white text-ink shadow-line"
                                        : "bg-transparent text-ink/75 hover:bg-white",
                                )}
                            >
                                <span className="block min-w-0 truncate text-sm font-medium">
                                    {session.title}
                                </span>
                            </button>

                            <button
                                type="button"
                                disabled={selectionDisabled}
                                onClick={(event) => {
                                    event.stopPropagation();
                                    setOpenMenuId(menuOpen ? null : session.session_id);
                                }}
                                className="absolute right-1 top-0 grid h-11 w-11 place-items-center rounded-lg text-ink/40 opacity-0 transition hover:bg-ink/5 hover:text-ink focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40 group-hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-35"
                                title="会话操作"
                                aria-label={`${session.title} 会话操作`}
                                aria-expanded={menuOpen}
                            >
                                <Ellipsis className="h-4 w-4" aria-hidden="true" />
                            </button>

                            {menuOpen && (
                                <div className="absolute right-2 top-12 z-20 w-32 border border-ink/15 bg-white py-1 shadow-panel">
                                    <button
                                        type="button"
                                        disabled={selectionDisabled}
                                        onClick={() => void runSessionAction(onRename, session).catch(() => undefined)}
                                        className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-xs text-ink/75 hover:bg-paper focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cinnabar/40"
                                    >
                                        <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                                        重命名
                                    </button>
                                    <button
                                        type="button"
                                        disabled={selectionDisabled}
                                        onClick={() => void runSessionAction(onArchive, session).catch(() => undefined)}
                                        className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-xs text-ink/75 hover:bg-paper focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cinnabar/40"
                                    >
                                        <Archive className="h-3.5 w-3.5" aria-hidden="true" />
                                        归档
                                    </button>
                                    <button
                                        type="button"
                                        disabled={selectionDisabled}
                                        onClick={() => void runSessionAction(onDelete, session).catch(() => undefined)}
                                        className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-xs text-oxide hover:bg-oxide/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cinnabar/40"
                                    >
                                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                                        删除
                                    </button>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {showHistoryLink && onOpenHistory && (
                <div className="flex justify-center pt-3">
                    <button
                        type="button"
                        disabled={disabled || loadingSessionId !== null || busySessionId !== null}
                        onClick={onOpenHistory}
                        className="min-h-10 px-3 text-xs font-medium text-ink/50 underline decoration-ink/20 underline-offset-4 transition hover:text-indigo focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40 disabled:cursor-not-allowed disabled:opacity-45"
                    >
                        查看所有
                    </button>
                </div>
            )}
        </section>
    );
}
