/**
 * 智能体接口客户端
 * 封装后端 /api/query SSE 流式接口请求与事件解析逻辑
 */
import { getAccessToken } from "../auth/keycloak";
import type { AgentEvent } from "../types/agent";
import type { ApplicationRole, ApplicationUserStatus } from "./userManagement";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

export type QuerySessionSummary = {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_request_id: string | null;
  last_outcome: string | null;
  last_query_mode: string | null;
  last_error_code: string | null;
  last_metadata_release_version: string | null;
};

type QueryOptions = {
  signal?: AbortSignal;
  onEvent: (event: AgentEvent) => void;
  sessionId?: string;
};

export async function streamQuery(query: string, options: QueryOptions) {
  const accessToken = await getAccessToken();
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ query, ...(options.sessionId ? { session_id: options.sessionId } : {}) }),
    signal: options.signal,
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("登录已失效，请重新登录");
    }
    if (response.status === 403) {
      throw new Error("没有执行该操作的权限");
    }
    throw new Error(`接口请求失败：HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error("浏览器未返回可读取的流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let cancelPromise: Promise<void> | undefined;
  const cancelReader = () => {
    cancelPromise ??= reader.cancel().catch(() => undefined);
  };
  options.signal?.addEventListener("abort", cancelReader, { once: true });

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split(/\n\n/);
      buffer = chunks.pop() ?? "";

      for (const chunk of chunks) {
        const event = parseSseChunk(chunk);
        if (event) {
          options.onEvent(event);
        }
      }
    }

    if (options.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }

    buffer += decoder.decode();
    const tail = parseSseChunk(buffer);
    if (tail) {
      options.onEvent(tail);
    }
  } finally {
    options.signal?.removeEventListener("abort", cancelReader);
    if (cancelPromise) {
      await cancelPromise;
    } else {
      await reader.cancel().catch(() => undefined);
    }
  }
}

export async function createQuerySession(title?: string): Promise<QuerySessionSummary> {
  const accessToken = await getAccessToken();
  const response = await fetch(`${API_BASE_URL}/api/sessions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(title ? { title } : {}),
  });
  if (!response.ok) {
    throw new Error(`会话创建失败：HTTP ${response.status}`);
  }
  return (await response.json()) as QuerySessionSummary;
}

export async function downloadQueryExport(exportId: string): Promise<Blob> {
  const accessToken = await getAccessToken();
  const response = await fetch(`${API_BASE_URL}/api/exports/${exportId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) {
    throw new Error(
      response.status === 410 ? "结果导出已过期" : `结果下载失败：HTTP ${response.status}`,
    );
  }
  return response.blob();
}

function parseSseChunk(chunk: string): AgentEvent | null {
  const payload = chunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace(/^data:\s?/, ""))
    .join("\n")
    .trim();

  if (!payload) return null;

  try {
    return JSON.parse(payload) as AgentEvent;
  } catch {
    return {
      type: "error",
      code: "sse_parse_error",
      message: `无法解析后端事件：${payload}`,
      retryable: false,
    };
  }
}

export type ApplicationUserSummary = {
    user_id: string;
    username: string | null;
    display_name: string | null;
    email: string | null;
    status: ApplicationUserStatus;
    keycloak_roles: string[];
    application_roles: ApplicationRole[];
    first_seen_at: string;
    last_seen_at: string;
    disabled_at: string | null;
};

export type ApplicationUserListResponse = {
    items: ApplicationUserSummary[];
    total: number;
    limit: number;
    offset: number;
};

export type ApplicationUserMeResponse = {
    user: ApplicationUserSummary;
    can_manage_users: boolean;
};

export type ApplicationUserDetailResponse = {
    user: ApplicationUserSummary;
    direct_policies: Array<{
        id: string;
        subject: string;
        resource: string;
        action: string;
        effect: string;
        version: number;
        active: boolean;
        created_by: string;
        created_at: string;
        revoked_at: string | null;
    }>;
    permission_preview: {
        user_id: string;
        roles: string[];
        policy_version: number;
        allowed_metrics: string[];
        allowed_tables: string[];
        allowed_columns: string[];
        allowed_department_ids: string[];
        sql_fallback_allowed: boolean;
    };
};

export type ApplicationUserListParams = {
    query?: string;
    status?: ApplicationUserStatus | "";
    role?: ApplicationRole | "";
    limit?: number;
    offset?: number;
};

async function getUserManagementJson<T>(
    path: string,
    init: RequestInit,
    action: string,
): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, init);
    if (!response.ok) {
        let code: string | undefined;
        let message: string | undefined;
        try {
            const payload: unknown = await response.json();
            if (payload !== null && typeof payload === "object" && "detail" in payload) {
                const detail = payload.detail;
                if (typeof detail === "string") message = detail;
                if (detail !== null && typeof detail === "object") {
                    if ("code" in detail && typeof detail.code === "string") code = detail.code;
                    if ("message" in detail && typeof detail.message === "string") message = detail.message;
                }
            }
        } catch {
            // 非 JSON 错误由状态码处理，不保留原始响应。
        }
        const safeMessage =
            message &&
            message.length <= 300 &&
            !/(?:bearer\s+\S+|authorization\s*[:=]|access[_-]?token\s*[:=]|refresh[_-]?token\s*[:=]|api[_-]?key\s*[:=]|password\s*[:=]|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b)/i.test(message)
                ? message
                : undefined;
        const error = new Error(safeMessage ?? `${action}：HTTP ${response.status}`) as Error & {
            status: number;
            code?: string;
        };
        error.status = response.status;
        if (code && /^[a-z][a-z0-9_]{0,63}$/.test(code)) error.code = code;
        throw error;
    }
    return (await response.json()) as T;
}

export async function getCurrentUserCapability(): Promise<ApplicationUserMeResponse> {
    const accessToken = await getAccessToken();
    return getUserManagementJson<ApplicationUserMeResponse>(
        "/api/admin/users/me",
        { headers: { Authorization: `Bearer ${accessToken}` } },
        "用户能力加载失败",
    );
}

export async function listApplicationUsers(
    params: ApplicationUserListParams = {},
): Promise<ApplicationUserListResponse> {
    const accessToken = await getAccessToken();
    const search = new URLSearchParams();
    if (params.query?.trim()) search.set("query", params.query.trim());
    if (params.status) search.set("status", params.status);
    if (params.role) search.set("role", params.role);
    search.set("limit", String(params.limit ?? 50));
    search.set("offset", String(params.offset ?? 0));
    return getUserManagementJson<ApplicationUserListResponse>(
        `/api/admin/users?${search.toString()}`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
        "用户列表加载失败",
    );
}

export async function getApplicationUser(userId: string): Promise<ApplicationUserDetailResponse> {
    const accessToken = await getAccessToken();
    return getUserManagementJson<ApplicationUserDetailResponse>(
        `/api/admin/users/${encodeURIComponent(userId)}`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
        "用户详情加载失败",
    );
}

export async function updateApplicationUserStatus(
    userId: string,
    status: ApplicationUserStatus,
    reason: string,
): Promise<ApplicationUserSummary> {
    const accessToken = await getAccessToken();
    return getUserManagementJson<ApplicationUserSummary>(
        `/api/admin/users/${encodeURIComponent(userId)}/status`,
        {
            method: "PATCH",
            headers: {
                Authorization: `Bearer ${accessToken}`,
                "Content-Type": "application/json",
                "Idempotency-Key": crypto.randomUUID(),
            },
            body: JSON.stringify({ status, reason }),
        },
        "用户状态更新失败",
    );
}

export async function replaceApplicationUserRoles(
    userId: string,
    roles: ApplicationRole[],
    reason: string,
): Promise<ApplicationUserSummary> {
    const accessToken = await getAccessToken();
    return getUserManagementJson<ApplicationUserSummary>(
        `/api/admin/users/${encodeURIComponent(userId)}/roles`,
        {
            method: "PUT",
            headers: {
                Authorization: `Bearer ${accessToken}`,
                "Content-Type": "application/json",
                "Idempotency-Key": crypto.randomUUID(),
            },
            body: JSON.stringify({ roles, reason }),
        },
        "应用角色更新失败",
    );
}
