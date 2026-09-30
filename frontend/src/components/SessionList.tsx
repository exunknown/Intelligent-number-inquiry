import {
    Archive,
    Clock3,
    Ellipsis,
    LoaderCircle,
    MessageCircle,
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
    onRename: (session: QuerySessionSummary) => void;
    onArchive: (session: QuerySessionSummary) => void;
    onDelete: (session: QuerySessionSummary) => void;
};

function formatSessionTime(value: string) {
    const timestamp = new Date(value);
    if (Number.isNaN(timestamp.getTime())) return "";
    return new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    }).format(timestamp);
}

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
}: SessionListProps) {
    const [openMenuId, setOpenMenuId] = useState<string | null>(null);

    return (
        <section aria-label="历史会话">
            <div className="mb-2 flex items-center justify-between px-1 text-xs font-semibold text-ink/45">
                <span className="inline-flex items-center gap-2">
                    <MessageCircle className="h-3.5 w-3.5" aria-hidden="true" />
                    历史会话
                </span>
                {loading && <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-label="加载中" />}
            </div>

            {error && (
                <div className="mb-2 border border-oxide/20 bg-oxide/5 px-3 py-2 text-xs leading-5 text-oxide">
                    {error}
                </div>
            )}

            {!loading && sessions.length === 0 && !error && (
                <div className="border border-dashed border-ink/15 px-3 py-4 text-center text-xs leading-5 text-ink/45">
                    还没有历史会话
                </div>
            )}

            <div className="space-y-1">
                {sessions.map((session) => {
                    const selected = session.session_id === selectedSessionId;
                    const menuOpen = session.session_id === openMenuId;
                    return (
                        <div key={session.session_id} className="relative">
                            <button
                                type="button"
                                disabled={disabled}
                                onClick={() => {
                                    setOpenMenuId(null);
                                    onSelect(session.session_id);
                                }}
                                aria-pressed={selected}
                                className={cn(
                                    "flex w-full min-w-0 items-start gap-2 border px-3 py-2.5 pr-10 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/45 disabled:cursor-not-allowed disabled:opacity-55",
                                    selected
                                        ? "border-indigo/30 bg-indigo/10"
                                        : "border-transparent hover:border-ink/10 hover:bg-white/70",
                                )}
                            >
                                <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-indigo/45" aria-hidden="true" />
                                <span className="min-w-0 flex-1">
                                    <span className="block truncate text-sm font-medium text-ink">
                                        {session.title}
                                    </span>
                                    <span className="mt-1 flex min-w-0 items-center gap-2 text-[11px] text-ink/45">
                                        <span className="inline-flex shrink-0 items-center gap-1">
                                            <Clock3 className="h-3 w-3" aria-hidden="true" />
                                            {formatSessionTime(session.updated_at)}
                                        </span>
                                        <span className="truncate">{session.message_count} 条消息</span>
                                    </span>
                                </span>
                            </button>

                            <button
                                type="button"
                                disabled={disabled}
                                onClick={(event) => {
                                    event.stopPropagation();
                                    setOpenMenuId(menuOpen ? null : session.session_id);
                                }}
                                className="absolute right-1.5 top-1.5 grid h-8 w-8 place-items-center text-ink/45 transition hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40 disabled:cursor-not-allowed disabled:opacity-35"
                                title="会话操作"
                                aria-label={`${session.title} 会话操作`}
                                aria-expanded={menuOpen}
                            >
                                <Ellipsis className="h-4 w-4" aria-hidden="true" />
                            </button>

                            {menuOpen && (
                                <div className="absolute right-2 top-10 z-20 w-32 border border-ink/15 bg-white py-1 shadow-panel">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setOpenMenuId(null);
                                            onRename(session);
                                        }}
                                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-ink/75 hover:bg-paper"
                                    >
                                        <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                                        重命名
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setOpenMenuId(null);
                                            onArchive(session);
                                        }}
                                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-ink/75 hover:bg-paper"
                                    >
                                        <Archive className="h-3.5 w-3.5" aria-hidden="true" />
                                        归档
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setOpenMenuId(null);
                                            onDelete(session);
                                        }}
                                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-oxide hover:bg-oxide/5"
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
        </section>
    );
}
