import { MessageCircle, Plus, X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { QuerySessionSummary } from "../lib/agentApi";
import { nextFocusableIndex } from "../lib/userManagement";
import { SessionList } from "./SessionList";

export type MobileSessionDrawerProps = {
    sessions: QuerySessionSummary[];
    selectedSessionId: string | null;
    loading: boolean;
    disabled: boolean;
    error: string | null;
    onNewSession: () => void;
    onSelect: (sessionId: string) => void;
    onRename: (session: QuerySessionSummary) => void;
    onArchive: (session: QuerySessionSummary) => void;
    onDelete: (session: QuerySessionSummary) => void;
    onClose: () => void;
};

const FOCUSABLE_SELECTOR = [
    "button:not([disabled])",
    "[href]",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

export function MobileSessionDrawer({
    sessions,
    selectedSessionId,
    loading,
    disabled,
    error,
    onNewSession,
    onSelect,
    onRename,
    onArchive,
    onDelete,
    onClose,
}: MobileSessionDrawerProps) {
    const dialogRef = useRef<HTMLDivElement>(null);
    const closeButtonRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        closeButtonRef.current?.focus();
    }, []);

    function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
        if (event.key === "Escape") {
            event.preventDefault();
            onClose();
            return;
        }

        if (event.key !== "Tab") return;

        const focusableElements = Array.from(
            dialogRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? [],
        );
        if (focusableElements.length === 0) return;

        const currentIndex = focusableElements.indexOf(document.activeElement as HTMLElement);
        const normalizedIndex = currentIndex === -1 ? (event.shiftKey ? 0 : -1) : currentIndex;
        const targetIndex = nextFocusableIndex(
            normalizedIndex,
            focusableElements.length,
            event.shiftKey ? "backward" : "forward",
        );

        event.preventDefault();
        focusableElements[targetIndex]?.focus();
    }

    return (
        <div className="absolute inset-0 z-30 lg:hidden" onKeyDown={handleKeyDown}>
            <button
                type="button"
                aria-label="关闭会话面板"
                className="absolute inset-0 bg-ink/20"
                onClick={onClose}
            />

            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="mobile-session-drawer-title"
                className="relative z-10 flex h-full w-[min(320px,88vw)] flex-col border-r border-ink/10 bg-paper shadow-panel"
            >
                <div className="flex items-center justify-between border-b border-ink/10 px-4 py-3">
                    <h2 id="mobile-session-drawer-title" className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                        <MessageCircle className="h-4 w-4 text-indigo" aria-hidden="true" />
                        移动端会话
                    </h2>
                    <button
                        ref={closeButtonRef}
                        type="button"
                        className="grid h-11 w-11 place-items-center text-ink/55 transition hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                        aria-label="关闭会话面板"
                        title="关闭会话面板"
                        onClick={onClose}
                    >
                        <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                </div>

                <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 py-3">
                    <button
                        type="button"
                        disabled={disabled}
                        className="mb-3 flex min-h-11 w-full items-center justify-center gap-2 border border-cinnabar/25 bg-cinnabar px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-cinnabar/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/45 disabled:cursor-not-allowed disabled:opacity-55"
                        onClick={() => {
                            onNewSession();
                            onClose();
                        }}
                    >
                        <Plus className="h-4 w-4" aria-hidden="true" />
                        新会话
                    </button>

                    <SessionList
                        sessions={sessions}
                        selectedSessionId={selectedSessionId}
                        loading={loading}
                        disabled={disabled}
                        error={error}
                        onSelect={(sessionId) => {
                            onSelect(sessionId);
                            onClose();
                        }}
                        onRename={onRename}
                        onArchive={onArchive}
                        onDelete={onDelete}
                    />
                </div>
            </div>
        </div>
    );
}
