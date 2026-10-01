import { ArrowLeft, ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
    searchQuerySessions,
    type QuerySessionPage,
    type QuerySessionSummary,
} from "../lib/agentApi";
import { SessionList } from "./SessionList";

const PAGE_SIZE = 10;

type HistoryPageProps = {
    selectedSessionId: string | null;
    onBack: () => void;
    onOpenSession: (sessionId: string) => void;
    onRename: (session: QuerySessionSummary) => Promise<void>;
    onArchive: (session: QuerySessionSummary) => Promise<void>;
    onDelete: (session: QuerySessionSummary) => Promise<void>;
};

const EMPTY_PAGE: QuerySessionPage = {
    items: [],
    total: 0,
    limit: PAGE_SIZE,
    offset: 0,
};

function getErrorMessage(error: unknown, fallback: string) {
    return error instanceof Error && error.message ? error.message : fallback;
}

export function HistoryPage({
    selectedSessionId,
    onBack,
    onOpenSession,
    onRename,
    onArchive,
    onDelete,
}: HistoryPageProps) {
    const [searchInput, setSearchInput] = useState("");
    const [page, setPage] = useState(1);
    const [pageData, setPageData] = useState<QuerySessionPage>(EMPTY_PAGE);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const requestGenerationRef = useRef(0);

    useEffect(() => {
        const generation = requestGenerationRef.current + 1;
        requestGenerationRef.current = generation;
        const timer = window.setTimeout(() => {
            setLoading(true);
            setError(null);
            void searchQuerySessions(searchInput.trim(), PAGE_SIZE, (page - 1) * PAGE_SIZE)
                .then((nextPage) => {
                    if (generation === requestGenerationRef.current) {
                        setPageData(nextPage);
                    }
                })
                .catch((requestError: unknown) => {
                    if (generation === requestGenerationRef.current) {
                        setError(getErrorMessage(requestError, "历史对话加载失败"));
                    }
                })
                .finally(() => {
                    if (generation === requestGenerationRef.current) {
                        setLoading(false);
                    }
                });
        }, 250);

        return () => window.clearTimeout(timer);
    }, [page, searchInput]);

    const reloadCurrentPage = async () => {
        const generation = requestGenerationRef.current + 1;
        requestGenerationRef.current = generation;
        setLoading(true);
        setError(null);
        try {
            const nextPage = await searchQuerySessions(
                searchInput.trim(),
                PAGE_SIZE,
                (page - 1) * PAGE_SIZE,
            );
            if (generation !== requestGenerationRef.current) return;
            if (nextPage.items.length === 0 && page > 1) {
                setPage(page - 1);
                return;
            }
            setPageData(nextPage);
        } catch (requestError: unknown) {
            if (generation === requestGenerationRef.current) {
                setError(getErrorMessage(requestError, "历史对话加载失败"));
            }
        } finally {
            if (generation === requestGenerationRef.current) {
                setLoading(false);
            }
        }
    };

    const runSessionAction = async (
        action: (session: QuerySessionSummary) => Promise<void>,
        session: QuerySessionSummary,
    ) => {
        try {
            await action(session);
            await reloadCurrentPage();
        } catch (actionError: unknown) {
            setError(getErrorMessage(actionError, "历史对话操作失败"));
        }
    };

    const totalPages = Math.max(1, Math.ceil(pageData.total / PAGE_SIZE));
    const startItem = pageData.total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const endItem = pageData.total === 0 ? 0 : Math.min(page * PAGE_SIZE, pageData.total);

    return (
        <main
            aria-labelledby="history-page-title"
            className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-paper px-4 py-5 sm:px-6 lg:px-10 lg:py-8"
        >
            <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col">
                <div className="flex items-start justify-between gap-4 border-b border-ink/10 pb-5">
                    <div>
                        <button
                            type="button"
                            onClick={onBack}
                            className="mb-4 inline-flex min-h-11 items-center gap-2 px-1 text-sm font-medium text-ink/60 transition hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                        >
                            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                            返回工作台
                        </button>
                        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                            <h1 id="history-page-title" className="font-serif text-3xl font-semibold text-ink">
                                历史对话
                            </h1>
                            <span className="text-sm text-ink/50">共 {pageData.total} 条</span>
                        </div>
                    </div>
                </div>

                <div className="mt-6 flex flex-col gap-3 border-b border-ink/10 pb-6 sm:flex-row sm:items-end">
                    <div className="min-w-0 flex-1">
                        <label htmlFor="history-search" className="mb-1.5 block text-sm font-medium text-ink">
                            搜索历史对话
                        </label>
                        <div className="relative">
                            <Search
                                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/40"
                                aria-hidden="true"
                            />
                            <input
                                id="history-search"
                                type="search"
                                value={searchInput}
                                onChange={(event) => {
                                    setSearchInput(event.target.value);
                                    setPage(1);
                                }}
                                placeholder="按标题或内容搜索"
                                className="h-11 w-full border border-ink/15 bg-white pl-10 pr-10 text-sm text-ink outline-none transition placeholder:text-ink/35 focus:border-indigo/45 focus:ring-2 focus:ring-indigo/15"
                            />
                            {searchInput && (
                                <button
                                    type="button"
                                    aria-label="清空搜索"
                                    title="清空搜索"
                                    onClick={() => {
                                        setSearchInput("");
                                        setPage(1);
                                    }}
                                    className="absolute right-1 top-1 grid h-9 w-9 place-items-center text-ink/45 transition hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                                >
                                    <X className="h-4 w-4" aria-hidden="true" />
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                <div className="mt-6 flex min-h-0 flex-1 flex-col">
                    <SessionList
                        sessions={pageData.items}
                        selectedSessionId={selectedSessionId}
                        loading={loading}
                        disabled={loading}
                        error={null}
                        onSelect={onOpenSession}
                        onRename={(session) => void runSessionAction(onRename, session)}
                        onArchive={(session) => void runSessionAction(onArchive, session)}
                        onDelete={(session) => void runSessionAction(onDelete, session)}
                        heading="历史对话"
                        emptyMessage="没有找到匹配的历史对话"
                        showHistoryLink={false}
                    />
                    {error && (
                        <p role="alert" className="mt-4 border border-oxide/20 bg-oxide/5 px-3 py-2 text-sm text-oxide">
                            {error}
                        </p>
                    )}
                </div>

                <div className="mt-6 flex flex-col gap-3 border-t border-ink/10 pt-4 text-sm text-ink/55 sm:flex-row sm:items-center sm:justify-between">
                    <span>
                        第 {startItem}-{endItem} 条，共 {pageData.total} 条
                    </span>
                    <div className="flex gap-2">
                        <button
                            type="button"
                            disabled={page <= 1}
                            onClick={() => setPage((currentPage) => currentPage - 1)}
                            className="flex h-11 items-center gap-1 border border-ink/15 px-3 font-medium text-ink/70 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                        >
                            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                            上一页
                        </button>
                        <button
                            type="button"
                            disabled={page >= totalPages}
                            onClick={() => setPage((currentPage) => currentPage + 1)}
                            className="flex h-11 items-center gap-1 border border-ink/15 px-3 font-medium text-ink/70 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                        >
                            下一页
                            <ChevronRight className="h-4 w-4" aria-hidden="true" />
                        </button>
                    </div>
                </div>
            </div>
        </main>
    );
}
