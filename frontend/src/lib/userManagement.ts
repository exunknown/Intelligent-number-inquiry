/** 应用用户管理的纯展示与错误规则。 */
export const APPLICATION_ROLES = [
    "platform_admin",
    "metric_governor",
    "analyst",
    "auditor",
] as const;

export type ApplicationRole = (typeof APPLICATION_ROLES)[number];
export type ApplicationUserStatus = "active" | "disabled";

const ROLE_LABELS: Record<ApplicationRole, string> = {
    platform_admin: "平台管理员",
    metric_governor: "指标治理员",
    analyst: "分析员",
    auditor: "审计员",
};

export function roleLabel(role: ApplicationRole): string {
    return ROLE_LABELS[role];
}

export function statusLabel(status: ApplicationUserStatus): string {
    return status === "active" ? "启用" : "禁用";
}

export function normalizeRoles(roles: readonly ApplicationRole[]): ApplicationRole[] {
    const selected = new Set(roles);
    return APPLICATION_ROLES.filter((role) => selected.has(role));
}

export function shouldAutoScrollChat(managementOpen: boolean): boolean {
    return !managementOpen;
}

export function nextFocusableIndex(
    currentIndex: number,
    length: number,
    direction: "forward" | "backward",
): number {
    if (length <= 0) return -1;
    const delta = direction === "forward" ? 1 : -1;
    return (currentIndex + delta + length) % length;
}

export function lastAdminInteraction(
    protectedAdmin: boolean,
    busy: boolean,
    status: ApplicationUserStatus,
    currentRoles: readonly ApplicationRole[],
    selectedRoles: readonly ApplicationRole[],
): { canEditRoles: boolean; canSaveRoles: boolean; canChangeStatus: boolean } {
    const removesAdmin = currentRoles.includes("platform_admin") && !selectedRoles.includes("platform_admin");
    return {
        canEditRoles: !busy,
        canSaveRoles: !busy && !(protectedAdmin && removesAdmin),
        canChangeStatus: !busy && !(protectedAdmin && status === "active"),
    };
}

export function mutationResultIsCurrent(
    targetUserId: string,
    startedGeneration: number,
    selectedUserId: string | null,
    currentGeneration: number,
): boolean {
    return targetUserId === selectedUserId && startedGeneration === currentGeneration;
}

type HttpError = { status?: unknown; code?: unknown; message?: unknown };

export function safeUserManagementMessage(value: unknown): string | null {
    if (typeof value !== "string") return null;
    const message = value.trim();
    if (!message || message.length > 300) return null;
    if (/(?:bearer|authorization|token|secret|password|cookie|headers?|api[-_]?key|eyJ[A-Za-z0-9_-]{10,}\.)/i.test(message)) {
        return null;
    }
    return message;
}

function errorParts(error: unknown): HttpError {
    return error !== null && typeof error === "object" ? (error as HttpError) : {};
}

export function mapUserManagementError(error: unknown): string {
    const { status, code, message } = errorParts(error);
    if (status === 401) return "登录已失效，请重新登录。";
    if (status === 403 && code === "user_disabled") return "账号已被禁用，请联系平台管理员。";
    if (status === 403) return "没有用户管理权限，请联系平台管理员。";
    if (status === 409 && code === "last_platform_admin") {
        return "不能移除或禁用最后一个平台管理员。请先指定另一位平台管理员。";
    }
    if (status === 409 && code === "idempotency_conflict") {
        return "本次请求与已有操作冲突，请刷新用户资料后重新提交。";
    }
    if (status === 422) return "角色、状态或原因不符合要求，请检查后重试。";
    if (status === 503) return "用户管理服务暂不可用，请稍后重试。";
    const safeMessage = safeUserManagementMessage(message);
    if (safeMessage) return safeMessage;
    return "操作未完成，请稍后重试。";
}

export function capabilityPresentation(
    canManageUsers: boolean | null,
    error: unknown,
): { showEntry: boolean; hint: string | null } {
    if (error === null) return { showEntry: canManageUsers === true, hint: null };
    const { status } = errorParts(error);
    if (status === 403) return { showEntry: false, hint: null };
    return { showEntry: false, hint: mapUserManagementError(error) };
}
