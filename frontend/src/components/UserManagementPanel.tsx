import {
    ArrowLeft,
    Ban,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Edit3,
    Eye,
    Plus,
    RefreshCw,
    Save,
    UserPlus,
    UsersRound,
    X,
} from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
    createApplicationUser,
    getApplicationUser,
    listApplicationUsers,
    replaceApplicationUserRoles,
    updateApplicationUser,
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
    validateApplicationUserEmail,
    validateTemporaryPassword,
    type ApplicationRole,
    type ApplicationUserStatus,
} from "../lib/userManagement";

const PAGE_SIZE = 20;
const controlClass =
    "h-11 w-full min-w-0 rounded-lg border border-ink/15 bg-white px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50";
const buttonClass =
    "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50 disabled:cursor-not-allowed disabled:opacity-45";
const iconButtonClass =
    "grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-ink/15 text-ink/70 hover:bg-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50 disabled:cursor-not-allowed disabled:opacity-45";

type DrawerMode = "closed" | "detail" | "create" | "edit";
type UserSelection = { userId: string | null; generation: number };
type DrawerContext = { mode: DrawerMode; selectedUserId: string | null; generation: number };
type UserProfileForm = {
    displayName: string;
    email: string;
    temporaryPassword: string;
};
type CreateUserForm = UserProfileForm & {
    username: string;
    applicationRoles: ApplicationRole[];
    enabled: boolean;
};
type FormFeedback = {
    kind: "success" | "error" | "info";
    message: string;
};

function emptyCreateForm(): CreateUserForm {
    return {
        username: "",
        displayName: "",
        email: "",
        temporaryPassword: "",
        applicationRoles: ["analyst"],
        enabled: true,
    };
}

function profileFormFromUser(user: ApplicationUserSummary): UserProfileForm {
    return {
        displayName: user.display_name ?? "",
        email: user.email ?? "",
        temporaryPassword: "",
    };
}

function displayName(user: ApplicationUserSummary): string {
    return user.display_name || user.username || user.user_id;
}

function seenAt(value: string): string {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "未知" : date.toLocaleString("zh-CN");
}

function feedbackClass(kind: FormFeedback["kind"]): string {
    if (kind === "success") return "text-pine";
    if (kind === "error") return "text-oxide";
    return "text-ink/70";
}

function roleSummary(roles: readonly ApplicationRole[]): string {
    return roles.length ? normalizeRoles(roles).map(roleLabel).join("、") : "暂无";
}

function toggleRole(roles: ApplicationRole[], role: ApplicationRole, checked: boolean): ApplicationRole[] {
    return normalizeRoles(checked ? [...roles, role] : roles.filter((item) => item !== role));
}

export function nextSelection(current: UserSelection, requestedUserId: string | null): UserSelection {
    if (current.userId === requestedUserId) return current;
    return { userId: requestedUserId, generation: current.generation + 1 };
}

export function nextDrawerContext(
    current: DrawerContext,
    mode: DrawerMode,
    selectedUserId: string | null,
): DrawerContext {
    if (current.mode === mode && current.selectedUserId === selectedUserId) return current;
    return { mode, selectedUserId, generation: current.generation + 1 };
}

export function drawerMutationIsCurrent(started: DrawerContext, current: DrawerContext): boolean {
    return (
        started.generation === current.generation &&
        started.mode === current.mode &&
        started.selectedUserId === current.selectedUserId
    );
}

export function UserManagementPanel({ onBack }: { onBack: () => void }) {
    const selectedUserRef = useRef<string | null>(null);
    const selectionGenerationRef = useRef(0);
    const drawerContextRef = useRef<DrawerContext>({
        mode: "closed",
        selectedUserId: null,
        generation: 0,
    });
    const drawerRef = useRef<HTMLElement | null>(null);
    const drawerOpenerRef = useRef<HTMLElement | null>(null);
    const [drawerMode, setDrawerMode] = useState<DrawerMode>("closed");
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
    const [busy, setBusy] = useState<"status" | "roles" | "create" | "edit" | null>(null);
    const [operationMessage, setOperationMessage] = useState<string | null>(null);
    const [lastAdminProtected, setLastAdminProtected] = useState(false);
    const [refreshKey, setRefreshKey] = useState(0);
    const [createForm, setCreateForm] = useState<CreateUserForm>(() => emptyCreateForm());
    const [editForm, setEditForm] = useState<UserProfileForm>(() => ({
        displayName: "",
        email: "",
        temporaryPassword: "",
    }));
    const [resetPassword, setResetPassword] = useState(false);
    const [createSubmitted, setCreateSubmitted] = useState(false);
    const [editSubmitted, setEditSubmitted] = useState(false);
    const [drawerFeedback, setDrawerFeedback] = useState<FormFeedback | null>(null);

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
                setEditForm(profileFormFromUser(response.user));
                setResetPassword(false);
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

    const rememberDrawerOpener = () => {
        if (document.activeElement instanceof HTMLElement) {
            drawerOpenerRef.current = document.activeElement;
        }
    };

    const restoreDrawerOpener = () => {
        const opener = drawerOpenerRef.current;
        window.setTimeout(() => opener?.focus(), 0);
    };

    const setDrawerContext = (mode: DrawerMode, selectedUserId: string | null) => {
        const next = nextDrawerContext(drawerContextRef.current, mode, selectedUserId);
        drawerContextRef.current = next;
        setDrawerMode(next.mode);
    };

    const openDetail = (userId: string) => {
        rememberDrawerOpener();
        selectUser(userId);
        setDrawerContext("detail", userId);
        setDrawerFeedback(null);
        setOperationMessage(null);
    };

    const openEdit = (userId: string) => {
        rememberDrawerOpener();
        selectUser(userId);
        setDrawerContext("edit", userId);
        setResetPassword(false);
        setEditSubmitted(false);
        setDrawerFeedback(null);
        setOperationMessage(null);
    };

    const closeDrawer = () => {
        setDrawerContext("closed", null);
        setCreateForm(emptyCreateForm());
        setCreateSubmitted(false);
        setEditSubmitted(false);
        setResetPassword(false);
        setEditForm((current) => ({ ...current, temporaryPassword: "" }));
        setDrawerFeedback(null);
        restoreDrawerOpener();
    };

    const changeFilters = () => {
        setOffset(0);
        selectUser(null);
        setDrawerContext("closed", null);
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

    const createErrors = {
        username: createSubmitted && !createForm.username.trim() ? "请输入用户名。" : null,
        displayName: createSubmitted && !createForm.displayName.trim() ? "请输入姓名。" : null,
        email: createSubmitted ? validateApplicationUserEmail(createForm.email).message : null,
        temporaryPassword: createSubmitted
            ? validateTemporaryPassword(createForm.temporaryPassword, { required: true }).message
            : null,
    };
    const editErrors = {
        displayName: editSubmitted && !editForm.displayName.trim() ? "请输入姓名。" : null,
        email: editSubmitted ? validateApplicationUserEmail(editForm.email).message : null,
        temporaryPassword: editSubmitted && resetPassword
            ? validateTemporaryPassword(editForm.temporaryPassword, { required: true }).message
            : null,
    };

    const submitCreate = async () => {
        const startedDrawerContext = drawerContextRef.current;
        setCreateSubmitted(true);
        setDrawerFeedback(null);
        const email = validateApplicationUserEmail(createForm.email);
        const password = validateTemporaryPassword(createForm.temporaryPassword, { required: true });
        if (!createForm.username.trim() || !createForm.displayName.trim() || !email.valid || !password.valid || busy) {
            setDrawerFeedback({ kind: "error", message: "请先修正表单中的提示。" });
            return;
        }
        setBusy("create");
        setDrawerFeedback({ kind: "info", message: "正在创建用户…" });
        try {
            const created = await createApplicationUser({
                username: createForm.username.trim(),
                display_name: createForm.displayName.trim(),
                email: createForm.email.trim(),
                temporary_password: createForm.temporaryPassword,
                application_roles: normalizeRoles(createForm.applicationRoles),
                enabled: createForm.enabled,
            });
            if (!drawerMutationIsCurrent(startedDrawerContext, drawerContextRef.current)) return;
            setCreateForm(emptyCreateForm());
            setCreateSubmitted(false);
            setDrawerFeedback({ kind: "success", message: "用户已创建。" });
            setOperationMessage("用户已创建。");
            selectUser(created.user_id);
            setDrawerContext("detail", created.user_id);
            setRefreshKey((value) => value + 1);
        } catch (error) {
            if (drawerMutationIsCurrent(startedDrawerContext, drawerContextRef.current)) {
                setDrawerFeedback({ kind: "error", message: mapUserManagementError(error) });
            }
        } finally {
            setBusy((current) => (current === "create" ? null : current));
        }
    };

    const submitEdit = async () => {
        if (!detail || busy) return;
        setEditSubmitted(true);
        setDrawerFeedback(null);
        const email = validateApplicationUserEmail(editForm.email);
        const password = validateTemporaryPassword(editForm.temporaryPassword, { required: resetPassword });
        if (!editForm.displayName.trim() || !email.valid || !password.valid) {
            setDrawerFeedback({ kind: "error", message: "请先修正表单中的提示。" });
            return;
        }
        const targetUserId = detail.user.user_id;
        const startedGeneration = selectionGenerationRef.current;
        const startedDrawerContext = drawerContextRef.current;
        const isCurrent = () => mutationResultIsCurrent(
            targetUserId,
            startedGeneration,
            selectedUserRef.current,
            selectionGenerationRef.current,
        ) && drawerMutationIsCurrent(startedDrawerContext, drawerContextRef.current);
        setBusy("edit");
        setDrawerFeedback({ kind: "info", message: "正在保存用户资料…" });
        try {
            await updateApplicationUser(targetUserId, {
                display_name: editForm.displayName.trim(),
                email: editForm.email.trim(),
                ...(resetPassword ? { temporary_password: editForm.temporaryPassword } : {}),
            });
            if (!isCurrent()) return;
            setResetPassword(false);
            setEditForm((current) => ({ ...current, temporaryPassword: "" }));
            setEditSubmitted(false);
            setDrawerFeedback({ kind: "success", message: "用户资料已更新。" });
            setOperationMessage("用户资料已更新。");
            setDrawerContext("detail", targetUserId);
            setRefreshKey((value) => value + 1);
        } catch (error) {
            if (isCurrent()) setDrawerFeedback({ kind: "error", message: mapUserManagementError(error) });
        } finally {
            setBusy((current) => (current === "edit" ? null : current));
        }
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
        if (!detail || busy) return;
        const targetUserId = detail.user.user_id;
        const startedGeneration = selectionGenerationRef.current;
        const nextStatus = detail.user.status === "active" ? "disabled" : "active";
        const trimmedReason = reason.trim();
        if (nextStatus === "disabled") {
            if (!trimmedReason) return;
            const confirmed = window.confirm("确定要禁用该用户吗？禁用后该用户将无法继续访问系统。");
            if (!confirmed) return;
        }
        const isCurrent = () => mutationResultIsCurrent(
            targetUserId,
            startedGeneration,
            selectedUserRef.current,
            selectionGenerationRef.current,
        );
        setBusy("status");
        setOperationMessage(null);
        try {
            await updateApplicationUserStatus(
                targetUserId,
                nextStatus,
                nextStatus === "active" ? (trimmedReason || "启用用户") : trimmedReason,
            );
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
    const drawerOpen = drawerMode !== "closed";

    useEffect(() => {
        if (!drawerOpen) return;
        window.setTimeout(() => {
            const drawer = drawerRef.current;
            if (!drawer) return;
            const firstFocusable = drawer.querySelector<HTMLElement>(
                'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
            );
            (firstFocusable ?? drawer).focus();
        }, 0);
    }, [drawerOpen, drawerMode]);

    const handleDrawerKeyDown = (event: KeyboardEvent<HTMLElement>) => {
        if (event.key === "Escape") {
            event.preventDefault();
            closeDrawer();
            return;
        }
        if (event.key !== "Tab") return;
        const drawer = drawerRef.current;
        if (!drawer) return;
        const focusable = Array.from(drawer.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )).filter((element) => !element.hasAttribute("disabled"));
        if (focusable.length === 0) {
            event.preventDefault();
            drawer.focus();
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    };

    return (
        <section
            role="region"
            aria-labelledby="user-management-title"
            className="min-h-0 flex-1 overflow-y-auto bg-canvas"
        >
            <div className="flex min-h-full flex-col bg-paper px-4 py-6 lg:px-7">
                <header className="flex min-h-20 shrink-0 items-center justify-between gap-3 border-b border-ink/10 px-5 py-4 lg:px-6">
                    <div className="flex min-w-0 items-center gap-3">
                        <UsersRound className="h-5 w-5 shrink-0 text-indigo" aria-hidden="true" />
                        <div className="min-w-0">
                            <h2 id="user-management-title" className="font-serif text-xl font-bold">用户目录与权限</h2>
                            <p className="mt-1 text-xs text-ink/60">表格管理用户档案，右侧抽屉处理创建、编辑、角色与状态变更。</p>
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
                            onClick={() => {
                                rememberDrawerOpener();
                                setCreateForm(emptyCreateForm());
                                setCreateSubmitted(false);
                                setDrawerFeedback(null);
                                setDrawerContext("create", null);
                            }}
                            className={`${buttonClass} bg-dai text-paper`}
                        >
                            <UserPlus className="h-4 w-4" aria-hidden="true" />
                            添加用户
                        </button>
                        <button
                            type="button"
                            onClick={() => setRefreshKey((value) => value + 1)}
                            title="刷新用户列表"
                            aria-label="刷新用户列表"
                            className={iconButtonClass}
                        >
                            <RefreshCw className="h-4 w-4" aria-hidden="true" />
                        </button>
                    </div>
                </header>

                <div className="min-w-0 p-4 lg:p-5">
                    <form
                        onSubmit={(event) => {
                            event.preventDefault();
                            changeFilters();
                            setQuery(searchInput.trim());
                            setRefreshKey((value) => value + 1);
                        }}
                        className="grid gap-3 border-b border-ink/10 pb-4 lg:grid-cols-[minmax(260px,1fr)_180px_190px_auto]"
                    >
                        <div className="min-w-0">
                            <label htmlFor="user-search" className="mb-1 block text-sm font-medium">搜索用户</label>
                            <input
                                id="user-search"
                                type="search"
                                value={searchInput}
                                onChange={(event) => setSearchInput(event.target.value)}
                                placeholder="姓名、用户名或用户 ID"
                                className={controlClass}
                            />
                        </div>
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
                        <div className="flex items-end">
                            <button type="submit" className={`${buttonClass} w-full bg-dai text-paper`}>搜索</button>
                        </div>
                    </form>

                    <div className="mt-4 flex items-center justify-between gap-3">
                        <div>
                            <h3 className="font-serif text-base font-bold">用户列表</h3>
                            <p className="mt-1 text-xs text-ink/60">共 {list?.total ?? 0} 人，点击行尾操作打开抽屉。</p>
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                type="button"
                                disabled={offset === 0 || listLoading}
                                onClick={() => {
                                    selectUser(null);
                                    setDrawerContext("closed", null);
                                    setOffset(Math.max(0, offset - PAGE_SIZE));
                                }}
                                title="上一页"
                                aria-label="上一页"
                                className={iconButtonClass}
                            >
                                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                            </button>
                            <span className="min-w-16 text-center text-xs text-ink/60">第 {Math.floor(offset / PAGE_SIZE) + 1} 页</span>
                            <button
                                type="button"
                                disabled={listLoading || !list || offset + list.limit >= list.total}
                                onClick={() => {
                                    selectUser(null);
                                    setDrawerContext("closed", null);
                                    setOffset(offset + PAGE_SIZE);
                                }}
                                title="下一页"
                                aria-label="下一页"
                                className={iconButtonClass}
                            >
                                <ChevronRight className="h-4 w-4" aria-hidden="true" />
                            </button>
                        </div>
                    </div>

                    {listError && <p role="alert" className="mt-4 text-sm text-oxide">{listError} 可重新搜索或翻页重试。</p>}

                    <div className="mt-4 overflow-x-auto rounded-xl border border-ink/10 bg-white">
                        <table className="w-full min-w-[1080px] table-fixed text-left text-sm">
                            <colgroup>
                                <col className="w-[18%]" />
                                <col className="w-[16%]" />
                                <col className="w-[21%]" />
                                <col className="w-[9%]" />
                                <col className="w-[18%]" />
                                <col className="w-[12%]" />
                                <col className="w-[6%]" />
                            </colgroup>
                            <thead className="bg-canvas text-xs text-ink/65">
                                <tr>
                                    <th scope="col" className="px-4 py-3 font-semibold">姓名</th>
                                    <th scope="col" className="px-4 py-3 font-semibold">用户名</th>
                                    <th scope="col" className="px-4 py-3 font-semibold">邮箱</th>
                                    <th scope="col" className="px-4 py-3 font-semibold">状态</th>
                                    <th scope="col" className="px-4 py-3 font-semibold">应用角色</th>
                                    <th scope="col" className="px-4 py-3 font-semibold">最后访问</th>
                                    <th scope="col" className="px-4 py-3 text-right font-semibold">操作</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-ink/10">
                                {listLoading && (
                                    <tr>
                                        <td colSpan={7} className="px-4 py-10 text-center text-sm text-ink/60">正在加载用户…</td>
                                    </tr>
                                )}
                                {!listLoading && list?.items.length === 0 && (
                                    <tr>
                                        <td colSpan={7} className="px-4 py-10 text-center text-sm text-ink/60">没有符合条件的用户。可调整搜索或筛选条件。</td>
                                    </tr>
                                )}
                                {!listLoading && list?.items.map((user) => (
                                    <tr
                                        key={user.user_id}
                                        className={selectedId === user.user_id ? "bg-indigo/5" : "bg-white hover:bg-paper"}
                                    >
                                        <td className="px-4 py-3 align-middle">
                                            <button
                                                type="button"
                                                onClick={() => openDetail(user.user_id)}
                                                className="max-w-full truncate font-medium text-ink underline-offset-4 hover:text-indigo hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                                                title={displayName(user)}
                                            >
                                                {displayName(user)}
                                            </button>
                                        </td>
                                        <td className="truncate px-4 py-3 align-middle text-ink/75" title={user.username ?? "未提供"}>{user.username || "未提供"}</td>
                                        <td className="truncate px-4 py-3 align-middle text-ink/75" title={user.email ?? "未提供"}>{user.email || "未提供"}</td>
                                        <td className="px-4 py-3 align-middle">
                                            <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${user.status === "active" ? "bg-pine/10 text-pine" : "bg-oxide/10 text-oxide"}`}>
                                                {statusLabel(user.status)}
                                            </span>
                                        </td>
                                        <td className="truncate px-4 py-3 align-middle text-ink/75" title={roleSummary(user.application_roles)}>
                                            {roleSummary(user.application_roles)}
                                        </td>
                                        <td className="truncate px-4 py-3 align-middle text-xs text-ink/60" title={seenAt(user.last_seen_at)}>{seenAt(user.last_seen_at)}</td>
                                        <td className="px-4 py-3 align-middle">
                                            <div className="flex justify-end gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => openDetail(user.user_id)}
                                                    title="查看用户详情"
                                                    aria-label={`查看用户详情：${displayName(user)}`}
                                                    className={iconButtonClass}
                                                >
                                                    <Eye className="h-4 w-4" aria-hidden="true" />
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => openEdit(user.user_id)}
                                                    title="编辑用户资料"
                                                    aria-label={`编辑用户资料：${displayName(user)}`}
                                                    className={iconButtonClass}
                                                >
                                                    <Edit3 className="h-4 w-4" aria-hidden="true" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            {drawerOpen && (
                <div className="fixed inset-0 z-40 flex justify-end bg-ink/20">
                    <aside
                        ref={drawerRef}
                        role="dialog"
                        aria-modal="true"
                        aria-label="用户详情抽屉"
                        tabIndex={-1}
                        onKeyDown={handleDrawerKeyDown}
                        className="h-full w-[560px] max-w-[calc(100vw-2rem)] overflow-y-auto border-l border-ink/15 bg-white shadow-panel"
                    >
                        <header className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-ink/10 bg-white px-6 py-5">
                            <div>
                                <p className="text-xs font-semibold text-indigo">
                                    USER MANAGEMENT · {drawerMode === "create" ? "CREATE" : selectedUser?.status.toUpperCase() ?? "LOADING"}
                                </p>
                                <h3 className="mt-1 font-serif text-2xl font-bold">
                                    {drawerMode === "create" ? "添加用户" : drawerMode === "edit" ? "编辑用户" : "用户详情"}
                                </h3>
                            </div>
                            <button
                                type="button"
                                onClick={closeDrawer}
                                title="关闭抽屉"
                                aria-label="关闭抽屉"
                                className={iconButtonClass}
                            >
                                <X className="h-4 w-4" aria-hidden="true" />
                            </button>
                        </header>

                        <div className="space-y-6 px-6 py-5">
                            {drawerMode === "create" && (
                                <form
                                    onSubmit={(event) => {
                                        event.preventDefault();
                                        void submitCreate();
                                    }}
                                    className="space-y-4"
                                >
                                    <div>
                                        <label htmlFor="create-username" className="mb-1 block text-sm font-semibold">用户名</label>
                                        <input
                                            id="create-username"
                                            value={createForm.username}
                                            onChange={(event) => setCreateForm((current) => ({ ...current, username: event.target.value }))}
                                            className={controlClass}
                                        />
                                        {createErrors.username && <p className="mt-1 text-xs text-oxide">{createErrors.username}</p>}
                                    </div>
                                    <div>
                                        <label htmlFor="create-display-name" className="mb-1 block text-sm font-semibold">姓名</label>
                                        <input
                                            id="create-display-name"
                                            value={createForm.displayName}
                                            onChange={(event) => setCreateForm((current) => ({ ...current, displayName: event.target.value }))}
                                            className={controlClass}
                                        />
                                        {createErrors.displayName && <p className="mt-1 text-xs text-oxide">{createErrors.displayName}</p>}
                                    </div>
                                    <div>
                                        <label htmlFor="create-email" className="mb-1 block text-sm font-semibold">邮箱</label>
                                        <input
                                            id="create-email"
                                            type="email"
                                            value={createForm.email}
                                            onChange={(event) => setCreateForm((current) => ({ ...current, email: event.target.value }))}
                                            className={controlClass}
                                        />
                                        {createErrors.email && <p className="mt-1 text-xs text-oxide">{createErrors.email}</p>}
                                    </div>
                                    <div>
                                        <label htmlFor="create-password" className="mb-1 block text-sm font-semibold">临时密码</label>
                                        <input
                                            id="create-password"
                                            type="password"
                                            value={createForm.temporaryPassword}
                                            onChange={(event) => setCreateForm((current) => ({ ...current, temporaryPassword: event.target.value }))}
                                            className={controlClass}
                                            autoComplete="new-password"
                                        />
                                        {createErrors.temporaryPassword && <p className="mt-1 text-xs text-oxide">{createErrors.temporaryPassword}</p>}
                                    </div>
                                    <fieldset className="border-t border-ink/10 pt-4">
                                        <legend className="text-sm font-semibold">应用角色</legend>
                                        <div className="mt-2 grid grid-cols-2 gap-1">
                                            {APPLICATION_ROLES.map((item) => (
                                                <label key={item} className="flex min-h-11 items-center gap-2 rounded-lg px-2 text-sm hover:bg-paper">
                                                    <input
                                                        type="checkbox"
                                                        checked={createForm.applicationRoles.includes(item)}
                                                        onChange={(event) => setCreateForm((current) => ({
                                                            ...current,
                                                            applicationRoles: toggleRole(current.applicationRoles, item, event.target.checked),
                                                        }))}
                                                        className="h-5 w-5 accent-indigo focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                                                    />
                                                    {roleLabel(item)}
                                                </label>
                                            ))}
                                        </div>
                                    </fieldset>
                                    <label className="flex min-h-11 items-center gap-2 rounded-lg text-sm">
                                        <input
                                            type="checkbox"
                                            checked={createForm.enabled}
                                            onChange={(event) => setCreateForm((current) => ({ ...current, enabled: event.target.checked }))}
                                            className="h-5 w-5 accent-indigo focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                                        />
                                        创建后立即启用
                                    </label>
                                    {drawerFeedback && (
                                        <p role={drawerFeedback.kind === "error" ? "alert" : "status"} className={`text-sm ${feedbackClass(drawerFeedback.kind)}`}>
                                            {drawerFeedback.message}
                                        </p>
                                    )}
                                    <div className="flex gap-2 border-t border-ink/10 pt-4">
                                        <button type="submit" disabled={busy === "create"} className={`${buttonClass} bg-dai text-paper`}>
                                            <Plus className="h-4 w-4" aria-hidden="true" />
                                            {busy === "create" ? "正在添加用户…" : "添加用户"}
                                        </button>
                                        <button type="button" onClick={closeDrawer} className={`${buttonClass} border border-ink/15 text-ink`}>取消</button>
                                    </div>
                                </form>
                            )}

                            {drawerMode !== "create" && (
                                <>
                                    {detailLoading && <p className="text-sm text-ink/60">正在加载详情…</p>}
                                    {detailError && (
                                        <div role="alert" className="text-sm text-oxide">
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
                                    {selectedUser && preview && drawerMode === "detail" && (
                                        <div className="space-y-5">
                                            <div className="flex items-center justify-between gap-3">
                                                <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${selectedUser.status === "active" ? "bg-pine/10 text-pine" : "bg-oxide/10 text-oxide"}`}>
                                                    {statusLabel(selectedUser.status)}
                                                </span>
                                                <button
                                                    type="button"
                                                    onClick={() => openEdit(selectedUser.user_id)}
                                                    className={`${buttonClass} border border-ink/15 text-ink`}
                                                >
                                                    <Edit3 className="h-4 w-4" aria-hidden="true" />
                                                    编辑资料
                                                </button>
                                            </div>
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
                                                <p className="text-xs text-ink/60">直接策略 {detail.direct_policies.length} 条 · SQL 回退{preview.sql_fallback_allowed ? "允许" : "不允许"} · 策略版本 {preview.policy_version}</p>
                                            </section>
                                            <section className="border-t border-ink/10 pt-4">
                                                <h4 className="text-sm font-semibold">应用角色</h4>
                                                <div className="mt-2 grid grid-cols-2 gap-1">
                                                    {APPLICATION_ROLES.map((item) => (
                                                        <label key={item} className="flex min-h-11 items-center gap-2 rounded-lg px-2 text-sm hover:bg-paper">
                                                            <input
                                                                type="checkbox"
                                                                checked={selectedRoles.includes(item)}
                                                                disabled={!interaction?.canEditRoles}
                                                                onChange={(event) => {
                                                                    setSelectedRoles((current) => toggleRole(current, item, event.target.checked));
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
                                                <label htmlFor="user-change-reason" className="mb-1 block text-sm font-semibold">
                                                    变更原因（角色或禁用时必填）
                                                </label>
                                                <textarea
                                                    id="user-change-reason"
                                                    value={reason}
                                                    maxLength={500}
                                                    onChange={(event) => setReason(event.target.value)}
                                                    placeholder="说明此次状态或角色变更的原因；启用用户可留空"
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
                                                    <Save className="h-4 w-4" aria-hidden="true" />
                                                    {busy === "roles" ? "正在保存角色…" : "保存应用角色"}
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => void changeStatus()}
                                                    disabled={
                                                        !interaction?.canChangeStatus ||
                                                        (selectedUser.status === "active" && !reason.trim())
                                                    }
                                                    className={`${buttonClass} border border-ink/15 text-ink`}
                                                >
                                                    {selectedUser.status === "active" ? <Ban className="h-4 w-4" aria-hidden="true" /> : <CheckCircle2 className="h-4 w-4" aria-hidden="true" />}
                                                    {busy === "status" ? "正在更新状态…" : selectedUser.status === "active" ? "禁用用户" : "启用用户"}
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {selectedUser && drawerMode === "edit" && (
                                        <form
                                            onSubmit={(event) => {
                                                event.preventDefault();
                                                void submitEdit();
                                            }}
                                            className="space-y-4"
                                        >
                                            <div>
                                                <label htmlFor="edit-display-name" className="mb-1 block text-sm font-semibold">姓名</label>
                                                <input
                                                    id="edit-display-name"
                                                    value={editForm.displayName}
                                                    onChange={(event) => setEditForm((current) => ({ ...current, displayName: event.target.value }))}
                                                    className={controlClass}
                                                />
                                                {editErrors.displayName && <p className="mt-1 text-xs text-oxide">{editErrors.displayName}</p>}
                                            </div>
                                            <div>
                                                <label htmlFor="edit-email" className="mb-1 block text-sm font-semibold">邮箱</label>
                                                <input
                                                    id="edit-email"
                                                    type="email"
                                                    value={editForm.email}
                                                    onChange={(event) => setEditForm((current) => ({ ...current, email: event.target.value }))}
                                                    className={controlClass}
                                                />
                                                {editErrors.email && <p className="mt-1 text-xs text-oxide">{editErrors.email}</p>}
                                            </div>
                                            <label className="flex min-h-11 items-center gap-2 rounded-lg text-sm">
                                                <input
                                                    type="checkbox"
                                                    checked={resetPassword}
                                                    onChange={(event) => {
                                                        setResetPassword(event.target.checked);
                                                        if (!event.target.checked) {
                                                            setEditForm((current) => ({ ...current, temporaryPassword: "" }));
                                                        }
                                                    }}
                                                    className="h-5 w-5 accent-indigo focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                                                />
                                                重置临时密码
                                            </label>
                                            {resetPassword && (
                                                <div>
                                                    <label htmlFor="edit-password" className="mb-1 block text-sm font-semibold">新的临时密码</label>
                                                    <input
                                                        id="edit-password"
                                                        type="password"
                                                        value={editForm.temporaryPassword}
                                                        onChange={(event) => setEditForm((current) => ({ ...current, temporaryPassword: event.target.value }))}
                                                        className={controlClass}
                                                        autoComplete="new-password"
                                                    />
                                                    {editErrors.temporaryPassword && <p className="mt-1 text-xs text-oxide">{editErrors.temporaryPassword}</p>}
                                                </div>
                                            )}
                                            {drawerFeedback && (
                                                <p role={drawerFeedback.kind === "error" ? "alert" : "status"} className={`text-sm ${feedbackClass(drawerFeedback.kind)}`}>
                                                    {drawerFeedback.message}
                                                </p>
                                            )}
                                            <div className="flex gap-2 border-t border-ink/10 pt-4">
                                                <button type="submit" disabled={busy === "edit"} className={`${buttonClass} bg-dai text-paper`}>
                                                    <Save className="h-4 w-4" aria-hidden="true" />
                                                    {busy === "edit" ? "正在保存资料…" : "保存资料"}
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setDrawerContext("detail", selectedUser.user_id);
                                                        setResetPassword(false);
                                                        setEditForm(profileFormFromUser(selectedUser));
                                                        setEditSubmitted(false);
                                                        setDrawerFeedback(null);
                                                    }}
                                                    className={`${buttonClass} border border-ink/15 text-ink`}
                                                >
                                                    取消
                                                </button>
                                            </div>
                                        </form>
                                    )}
                                </>
                            )}
                        </div>
                    </aside>
                </div>
            )}
        </section>
    );
}
