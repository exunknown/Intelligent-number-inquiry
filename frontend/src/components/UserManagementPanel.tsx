import { ArrowLeft, ChevronLeft, ChevronRight, RefreshCw, UsersRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
    getApplicationUser,
    listApplicationUsers,
    replaceApplicationUserRoles,
    updateApplicationUserStatus,
    type ApplicationUserDetailResponse,
    type ApplicationUserListResponse,
    type ApplicationUserSummary,
} from "../lib/agentApi";
import {
    APPLICATION_ROLES,
    lastAdminInteraction,
    mapUserManagementError,
    mutationResultIsCurrent,
    normalizeRoles,
    roleLabel,
    statusLabel,
    type ApplicationRole,
    type ApplicationUserStatus,
} from "../lib/userManagement";

const PAGE_SIZE = 20;
const controlClass =
    "h-11 w-full min-w-0 rounded-lg border border-ink/15 bg-white px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50";
const buttonClass =
    "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50 disabled:cursor-not-allowed disabled:opacity-45";

function displayName(user: ApplicationUserSummary): string {
    return user.display_name || user.username || user.user_id;
}

function seenAt(value: string): string {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "未知" : date.toLocaleString("zh-CN");
}

type UserSelection = { userId: string | null; generation: number };

export function nextSelection(current: UserSelection, requestedUserId: string | null): UserSelection {
    if (current.userId === requestedUserId) return current;
    return { userId: requestedUserId, generation: current.generation + 1 };
}

export function UserManagementPanel({ onBack }: { onBack: () => void }) {
    const selectedUserRef = useRef<string | null>(null);
    const selectionGenerationRef = useRef(0);
    const [searchInput, setSearchInput] = useState("");
    const [query, setQuery] = useState("");
    const [status, setStatus] = useState<ApplicationUserStatus | "">("");
    const [role, setRole] = useState<ApplicationRole | "">("");
    const [offset, setOffset] = useState(0);
    const [list, setList] = useState<ApplicationUserListResponse | null>(null);
    const [listLoading, setListLoading] = useState(true);
    const [listError, setListError] = useState<string | null>(null);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [detail, setDetail] = useState<ApplicationUserDetailResponse | null>(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState<string | null>(null);
    const [selectedRoles, setSelectedRoles] = useState<ApplicationRole[]>([]);
    const [reason, setReason] = useState("");
    const [busy, setBusy] = useState<"status" | "roles" | null>(null);
    const [operationMessage, setOperationMessage] = useState<string | null>(null);
    const [lastAdminProtected, setLastAdminProtected] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);

    useEffect(() => {
        let current = true;
        setListLoading(true);
        setList(null);
        setListError(null);
        void listApplicationUsers({ query, status, role, limit: PAGE_SIZE, offset })
            .then((response) => {
                if (current) setList(response);
            })
            .catch((error: unknown) => {
                if (current) setListError(mapUserManagementError(error));
            })
            .finally(() => {
                if (current) setListLoading(false);
            });
        return () => {
            current = false;
        };
    }, [query, status, role, offset, refreshKey]);

    useEffect(() => {
        if (!selectedId) {
            setDetail(null);
            return;
        }
        let current = true;
        setDetail(null);
        setDetailLoading(true);
        setDetailError(null);
        setLastAdminProtected(false);
        void getApplicationUser(selectedId)
            .then((response) => {
                if (!current) return;
                setDetail(response);
                setSelectedRoles(normalizeRoles(response.user.application_roles));
                setReason("");
            })
            .catch((error: unknown) => {
                if (current) setDetailError(mapUserManagementError(error));
            })
            .finally(() => {
                if (current) setDetailLoading(false);
            });
        return () => {
            current = false;
        };
    }, [selectedId, refreshKey]);

    const selectUser = (userId: string | null) => {
        const current = {
            userId: selectedUserRef.current,
            generation: selectionGenerationRef.current,
        };
        const next = nextSelection(current, userId);
        if (next === current) return;
        selectedUserRef.current = next.userId;
        selectionGenerationRef.current = next.generation;
        setSelectedId(next.userId);
    };

    const changeFilters = () => {
        setOffset(0);
        selectUser(null);
        setOperationMessage(null);
    };

    const handleError = (error: unknown) => {
        if (
            error !== null &&
            typeof error === "object" &&
            "code" in error &&
            error.code === "last_platform_admin"
        ) {
            setLastAdminProtected(true);
        }
        setOperationMessage(mapUserManagementError(error));
    };

    const saveRoles = async () => {
        if (!detail || !reason.trim() || busy) return;
        const targetUserId = detail.user.user_id;
        const startedGeneration = selectionGenerationRef.current;
        const isCurrent = () => mutationResultIsCurrent(
            targetUserId,
            startedGeneration,
            selectedUserRef.current,
            selectionGenerationRef.current,
        );
        setBusy("roles");
        setOperationMessage(null);
        try {
            await replaceApplicationUserRoles(targetUserId, normalizeRoles(selectedRoles), reason.trim());
            if (!isCurrent()) return;
            setLastAdminProtected(false);
            setOperationMessage("应用角色已更新。");
            setRefreshKey((value) => value + 1);
        } catch (error) {
            if (isCurrent()) handleError(error);
        } finally {
            setBusy(null);
        }
    };

    const changeStatus = async () => {
        if (!detail || !reason.trim() || busy) return;
        const targetUserId = detail.user.user_id;
        const startedGeneration = selectionGenerationRef.current;
        const isCurrent = () => mutationResultIsCurrent(
            targetUserId,
            startedGeneration,
            selectedUserRef.current,
            selectionGenerationRef.current,
        );
        const nextStatus = detail.user.status === "active" ? "disabled" : "active";
        setBusy("status");
        setOperationMessage(null);
        try {
            await updateApplicationUserStatus(targetUserId, nextStatus, reason.trim());
            if (!isCurrent()) return;
            setLastAdminProtected(false);
            setOperationMessage(nextStatus === "active" ? "用户已启用。" : "用户已禁用。");
            setRefreshKey((value) => value + 1);
        } catch (error) {
            if (isCurrent()) handleError(error);
        } finally {
            setBusy(null);
        }
    };

    const selectedUser = detail?.user;
    const rolesChanged = selectedUser
        ? normalizeRoles(selectedRoles).join("|") !== normalizeRoles(selectedUser.application_roles).join("|")
        : false;
    const interaction = selectedUser
        ? lastAdminInteraction(lastAdminProtected, busy !== null, selectedUser.status, selectedUser.application_roles, selectedRoles)
        : null;
    const preview = detail?.permission_preview;

    return (
        <section
            role="region"
            aria-labelledby="user-management-title"
            className="min-h-0 flex-1 overflow-y-auto bg-canvas px-4 py-6 lg:px-7"
        >
            <div className="mx-auto min-h-full max-w-6xl overflow-hidden rounded-xl border border-ink/15 bg-paper shadow-line">
                <header className="flex min-h-20 shrink-0 items-center justify-between gap-3 border-b border-ink/10 px-5 py-4 lg:px-6">
                    <div className="flex min-w-0 items-center gap-3">
                        <UsersRound className="h-5 w-5 shrink-0 text-indigo" aria-hidden="true" />
                        <div className="min-w-0">
                            <h2 id="user-management-title" className="font-serif text-xl font-bold">用户目录与权限</h2>
                            <p className="mt-1 text-xs text-ink/60">仅展示已访问本系统的用户，变更操作需要填写原因。</p>
                        </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                        <button
                            type="button"
                            onClick={onBack}
                            className={`${buttonClass} border border-ink/15 text-ink`}
                        >
                            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                            返回工作台
                        </button>
                        <button
                            type="button"
                            onClick={() => setRefreshKey((value) => value + 1)}
                            title="刷新用户列表"
                            aria-label="刷新用户列表"
                            className="grid h-11 w-11 place-items-center rounded-lg border border-ink/15 text-ink/70 hover:bg-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                        >
                            <RefreshCw className="h-4 w-4" aria-hidden="true" />
                        </button>
                    </div>
                </header>

                <div className="grid min-w-0 lg:grid-cols-[360px_minmax(0,1fr)]">
                    <section aria-label="用户列表" className="min-w-0 border-b border-ink/10 p-4 lg:border-b-0 lg:border-r lg:p-5">
                        <div className="mb-4 flex items-center justify-between gap-3">
                            <h3 className="font-serif text-base font-bold">用户列表</h3>
                            <span className="text-xs text-ink/60">共 {list?.total ?? 0} 人</span>
                        </div>
                        <form
                            onSubmit={(event) => {
                                event.preventDefault();
                                changeFilters();
                                setQuery(searchInput.trim());
                                setRefreshKey((value) => value + 1);
                            }}
                            className="space-y-3"
                        >
                            <div>
                                <label htmlFor="user-search" className="mb-1 block text-sm font-medium">搜索用户</label>
                                <div className="flex min-w-0 gap-2">
                                    <input
                                        id="user-search"
                                        type="search"
                                        value={searchInput}
                                        onChange={(event) => setSearchInput(event.target.value)}
                                        placeholder="姓名、用户名或用户 ID"
                                        className={controlClass}
                                    />
                                    <button type="submit" className={`${buttonClass} shrink-0 bg-dai text-paper`}>搜索</button>
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div className="min-w-0">
                                    <label htmlFor="user-status" className="mb-1 block text-sm font-medium">状态</label>
                                    <select
                                        id="user-status"
                                        value={status}
                                        onChange={(event) => {
                                            changeFilters();
                                            setStatus(event.target.value as ApplicationUserStatus | "");
                                        }}
                                        className={controlClass}
                                    >
                                        <option value="">全部状态</option>
                                        <option value="active">启用</option>
                                        <option value="disabled">禁用</option>
                                    </select>
                                </div>
                                <div className="min-w-0">
                                    <label htmlFor="user-role" className="mb-1 block text-sm font-medium">应用角色</label>
                                    <select
                                        id="user-role"
                                        value={role}
                                        onChange={(event) => {
                                            changeFilters();
                                            setRole(event.target.value as ApplicationRole | "");
                                        }}
                                        className={controlClass}
                                    >
                                        <option value="">全部角色</option>
                                        {APPLICATION_ROLES.map((item) => (
                                            <option key={item} value={item}>{roleLabel(item)}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                        </form>
                        {listError && <p role="alert" className="mt-4 text-sm text-oxide">{listError} 可重新搜索或翻页重试。</p>}
                        <div aria-live="polite" className="mt-4 space-y-2">
                            {listLoading ? (
                                <p className="py-6 text-sm text-ink/60">正在加载用户…</p>
                            ) : list?.items.length ? (
                                list.items.map((user) => (
                                    <button
                                        key={user.user_id}
                                        type="button"
                                        onClick={() => {
                                            selectUser(user.user_id);
                                            setOperationMessage(null);
                                        }}
                                        aria-pressed={selectedId === user.user_id}
                                        className={`w-full min-w-0 rounded-lg border px-3 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50 ${selectedId === user.user_id ? "border-indigo bg-indigo/5" : "border-ink/10 bg-paper hover:border-indigo/40"}`}
                                    >
                                        <span className="flex min-w-0 items-center justify-between gap-2">
                                            <span className="min-w-0 truncate font-medium" title={displayName(user)}>{displayName(user)}</span>
                                            <span className={`shrink-0 text-xs ${user.status === "active" ? "text-pine" : "text-oxide"}`}>{statusLabel(user.status)}</span>
                                        </span>
                                        <span className="mt-1 block text-xs text-ink/60">最后访问 {seenAt(user.last_seen_at)}</span>
                                    </button>
                                ))
                            ) : (
                                <p className="py-6 text-sm text-ink/60">没有符合条件的用户。可调整搜索或筛选条件。</p>
                            )}
                        </div>
                        <div className="mt-4 flex items-center justify-between gap-2 border-t border-ink/10 pt-4">
                            <button
                                type="button"
                                disabled={offset === 0 || listLoading}
                                onClick={() => {
                                    selectUser(null);
                                    setOffset(Math.max(0, offset - PAGE_SIZE));
                                }}
                                className={`${buttonClass} border border-ink/15`}
                            >
                                <ChevronLeft className="h-4 w-4" aria-hidden="true" />上一页
                            </button>
                            <span className="text-xs text-ink/60">第 {Math.floor(offset / PAGE_SIZE) + 1} 页</span>
                            <button
                                type="button"
                                disabled={listLoading || !list || offset + list.limit >= list.total}
                                onClick={() => {
                                    selectUser(null);
                                    setOffset(offset + PAGE_SIZE);
                                }}
                                className={`${buttonClass} border border-ink/15`}
                            >
                                下一页<ChevronRight className="h-4 w-4" aria-hidden="true" />
                            </button>
                        </div>
                    </section>

                    <section aria-label="用户详情" className="min-w-0 bg-white p-4 lg:p-6">
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <p className="text-xs font-semibold tracking-[0.08em] text-indigo">
                                    USER PROFILE · {selectedUser?.status.toUpperCase() ?? "IDLE"}
                                </p>
                                <h3 className="mt-1 font-serif text-2xl font-bold">用户详情</h3>
                            </div>
                            {selectedUser && (
                                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${selectedUser.status === "active" ? "bg-pine/10 text-pine" : "bg-oxide/10 text-oxide"}`}>
                                    {statusLabel(selectedUser.status)}
                                </span>
                            )}
                        </div>
                        {!selectedId && <p className="mt-6 text-sm text-ink/60">从左侧列表选择一位用户，查看档案和权限。</p>}
                        {detailLoading && <p className="mt-6 text-sm text-ink/60">正在加载详情…</p>}
                        {detailError && (
                            <div role="alert" className="mt-4 text-sm text-oxide">
                                <p>{detailError} 可重试加载详情。</p>
                                <button
                                    type="button"
                                    onClick={() => setRefreshKey((value) => value + 1)}
                                    className={`${buttonClass} mt-2 border border-ink/15 text-ink`}
                                >
                                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                                    重试加载
                                </button>
                            </div>
                        )}
                        {selectedUser && preview && (
                            <div className="mt-4 space-y-5">
                                <div className="grid gap-2 sm:grid-cols-2">
                                    {[
                                        ["可访问指标", preview.allowed_metrics.length],
                                        ["可访问数据表", preview.allowed_tables.length],
                                        ["可访问列", preview.allowed_columns.length],
                                        ["部门策略", preview.allowed_department_ids.length],
                                    ].map(([label, value]) => (
                                        <div key={label} className="border border-ink/10 bg-paper px-3 py-3">
                                            <div className="font-serif text-2xl font-bold text-indigo">{value}</div>
                                            <div className="mt-1 text-xs text-ink/60">{label}</div>
                                        </div>
                                    ))}
                                </div>
                                <dl className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 border-b border-ink/10 pb-4 text-sm">
                                    <dt className="text-ink/60">姓名</dt><dd className="min-w-0 break-words font-medium">{displayName(selectedUser)}</dd>
                                    <dt className="text-ink/60">用户名</dt><dd className="min-w-0 break-all">{selectedUser.username || "未提供"}</dd>
                                    <dt className="text-ink/60">邮箱</dt><dd className="min-w-0 break-all">{selectedUser.email || "未提供"}</dd>
                                    <dt className="text-ink/60">用户 ID</dt><dd className="min-w-0 break-all font-mono text-xs">{selectedUser.user_id}</dd>
                                    <dt className="text-ink/60">状态</dt><dd>{statusLabel(selectedUser.status)}</dd>
                                    <dt className="text-ink/60">首次访问</dt><dd>{seenAt(selectedUser.first_seen_at)}</dd>
                                    <dt className="text-ink/60">最后访问</dt><dd>{seenAt(selectedUser.last_seen_at)}</dd>
                                </dl>
                                <section>
                                    <h4 className="text-sm font-semibold">Keycloak 角色 · 最近观测</h4>
                                    <p className="mt-1 text-xs text-ink/60">该用户下次访问后才会更新观测值。</p>
                                    <p className="mt-2 break-words text-sm">{selectedUser.keycloak_roles.length ? selectedUser.keycloak_roles.join("、") : "暂无"}</p>
                                </section>
                                <section className="border-t border-ink/10 pt-4">
                                    <h4 className="text-sm font-semibold">有效权限摘要</h4>
                                    <p className="mt-2 text-sm leading-6 text-ink/75">
                                        指标 {preview.allowed_metrics.length} · 表 {preview.allowed_tables.length} · 列 {preview.allowed_columns.length} · 部门 {preview.allowed_department_ids.length}
                                    </p>
                                    <p className="text-xs text-ink/60">直接策略 {detail!.direct_policies.length} 条 · SQL 回退{preview.sql_fallback_allowed ? "允许" : "不允许"} · 策略版本 {preview.policy_version}</p>
                                </section>
                                <section className="border-t border-ink/10 pt-4">
                                    <h4 className="text-sm font-semibold">应用角色</h4>
                                    <div className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
                                        {APPLICATION_ROLES.map((item) => (
                                            <label key={item} className="flex min-h-11 items-center gap-2 rounded-lg px-2 text-sm hover:bg-paper">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedRoles.includes(item)}
                                                    disabled={!interaction?.canEditRoles}
                                                    onChange={(event) => {
                                                        setSelectedRoles((current) => normalizeRoles(event.target.checked ? [...current, item] : current.filter((roleItem) => roleItem !== item)));
                                                        setOperationMessage(null);
                                                    }}
                                                    className="h-5 w-5 accent-indigo focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                                                />
                                                {roleLabel(item)}
                                            </label>
                                        ))}
                                    </div>
                                </section>
                                <div>
                                    <label htmlFor="user-change-reason" className="mb-1 block text-sm font-semibold">变更原因（必填）</label>
                                    <textarea
                                        id="user-change-reason"
                                        value={reason}
                                        maxLength={500}
                                        onChange={(event) => setReason(event.target.value)}
                                        placeholder="说明此次状态或角色变更的原因"
                                        className={`${controlClass} min-h-24 py-2`}
                                    />
                                </div>
                                {lastAdminProtected && (
                                    <p role="alert" className="text-sm text-oxide">最后一个平台管理员受到保护。请先为其他用户分配平台管理员角色，再重试此变更。</p>
                                )}
                                {operationMessage && <p role="status" aria-live="polite" className="text-sm text-ink/75">{operationMessage}</p>}
                                <div className="flex flex-wrap gap-2">
                                    <button
                                        type="button"
                                        onClick={() => void saveRoles()}
                                        disabled={!reason.trim() || !rolesChanged || !interaction?.canSaveRoles}
                                        className={`${buttonClass} bg-dai text-paper`}
                                    >
                                        {busy === "roles" ? "正在保存角色…" : "保存应用角色"}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => void changeStatus()}
                                        disabled={!reason.trim() || !interaction?.canChangeStatus}
                                        className={`${buttonClass} border border-ink/15 text-ink`}
                                    >
                                        {busy === "status" ? "正在更新状态…" : selectedUser.status === "active" ? "禁用用户" : "启用用户"}
                                    </button>
                                </div>
                            </div>
                        )}
                    </section>
                </div>
            </div>
        </section>
    );
}
