/**
 * 智能体接口客户端
 * 封装后端 /api/query SSE 流式接口请求与事件解析逻辑
 */
import { getAccessToken } from "../auth/keycloak";
import type { AgentEvent } from "../types/agent";
import type {
    SemanticDraft,
    SemanticMember,
    SemanticMemberSummary,
    SemanticOperation,
    SemanticRelease,
    SemanticSnapshot,
    SemanticValidationIssue,
} from "./semanticModel";
import { safeUserManagementMessage, type ApplicationRole, type ApplicationUserStatus } from "./userManagement";

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
  archived_at?: string | null;
};

export type QuerySessionPage = {
  items: QuerySessionSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type QueryMessageResponse = {
  message_id: string;
  session_id: string;
  request_id: string | null;
  sequence_no: number;
  role: "user" | "assistant";
  content: string;
  status: "done" | "error" | "cancelled" | "streaming";
  steps: Record<string, string> | null;
  metrics: string[] | null;
  query_mode: string | null;
  route_reason: string | null;
  result_preview: unknown;
  verified: boolean | null;
  warning: string | null;
  row_count: number | null;
  truncated: boolean | null;
  export_id: string | null;
  error: string | null;
  error_code: string | null;
  retryable: boolean | null;
  created_at: string;
};

export type QuerySessionAuditMessage = {
  request_id: string | null;
  created_at: string;
  query_text: string;
  outcome: string;
  query_mode: string | null;
  route_reason: string | null;
  verified: boolean | null;
  error_code: string | null;
  duration_ms: number;
  metadata_release_version: string | null;
  result_row_count: number | null;
  result_bytes: number | null;
  result_truncated: boolean | null;
};

export type QuerySessionMessage = QueryMessageResponse | QuerySessionAuditMessage;

export type QuerySessionDetail = {
  session: QuerySessionSummary;
  messages: QuerySessionMessage[];
};

export type QueryOptions = {
  signal?: AbortSignal;
  onEvent: (event: AgentEvent) => void;
  onEventId?: (eventId: string) => void;
  sessionId?: string;
};

type ReplayQueryOptions = QueryOptions & {
  onReplayAttempt?: () => void;
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

  ensureStreamResponse(response, "接口请求失败");
  await consumeSseResponse(response, options);
}

export async function replayQueryEvents(
  requestId: string,
  lastEventId: string | null,
  options: QueryOptions,
) {
  const accessToken = await getAccessToken();
  const headers: HeadersInit = {
    Authorization: `Bearer ${accessToken}`,
  };
  if (lastEventId) {
    headers["Last-Event-ID"] = lastEventId;
  }
  const response = await fetch(
    `${API_BASE_URL}/api/query/events/${encodeURIComponent(requestId)}`,
    {
      headers,
      signal: options.signal,
    },
  );

  ensureStreamResponse(response, "重放查询事件失败");
  await consumeSseResponse(response, options);
}

export async function streamQueryWithReplay(
  query: string,
  options: ReplayQueryOptions,
) {
  let requestId: string | null = null;
  let lastEventId: string | null = null;

  const onEventId = (eventId: string) => {
    const separator = eventId.lastIndexOf(":");
    if (separator > 0 && separator < eventId.length - 1) {
      requestId = eventId.slice(0, separator);
      lastEventId = eventId;
    }
    options.onEventId?.(eventId);
  };
  const streamOptions = { ...options, onEventId };

  try {
    await streamQuery(query, streamOptions);
  } catch (error) {
    const isAbort = error instanceof DOMException && error.name === "AbortError";
    if (isAbort || !requestId || !lastEventId) {
      throw error;
    }
    options.onReplayAttempt?.();
    await replayQueryEvents(requestId, lastEventId, streamOptions);
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

async function getJson<T>(
    path: string,
    init: RequestInit,
    action: string,
    unavailableMessage?: string,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (error) {
    if (unavailableMessage) throw new Error(unavailableMessage);
    throw error;
  }
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("登录已失效，请重新登录");
    }
    if (response.status === 403) {
      throw new Error("没有执行该操作的权限");
    }
    if (unavailableMessage && response.status >= 500) {
      throw new Error(unavailableMessage);
    }
    throw new Error(`${action}：HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function listQuerySessions(
  limit = 50,
  offset = 0,
): Promise<QuerySessionSummary[]> {
  const accessToken = await getAccessToken();
  return getJson<QuerySessionSummary[]>(
    `/api/sessions?limit=${limit}&offset=${offset}`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
    },
    "会话列表加载失败",
  );
}

export async function searchQuerySessions(
  query = "",
  limit = 10,
  offset = 0,
): Promise<QuerySessionPage> {
  const accessToken = await getAccessToken();
  const params = new URLSearchParams({
    query,
    limit: String(limit),
    offset: String(offset),
  });
  return getJson<QuerySessionPage>(
    `/api/sessions/history?${params.toString()}`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
    },
    "历史对话加载失败",
    "历史对话加载失败，请稍后重试",
  );
}

export async function getQuerySession(
  sessionId: string,
  limit = 100,
  offset = 0,
): Promise<QuerySessionDetail> {
  const accessToken = await getAccessToken();
  return getJson<QuerySessionDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}?limit=${limit}&offset=${offset}`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
    },
    "会话详情加载失败",
  );
}

export async function updateQuerySessionTitle(
  sessionId: string,
  title: string,
): Promise<QuerySessionSummary> {
  const accessToken = await getAccessToken();
  return getJson<QuerySessionSummary>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title }),
    },
    "会话重命名失败",
  );
}

export async function archiveQuerySession(sessionId: string): Promise<QuerySessionSummary> {
  const accessToken = await getAccessToken();
  return getJson<QuerySessionSummary>(
    `/api/sessions/${encodeURIComponent(sessionId)}/archive`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    },
    "会话归档失败",
  );
}

export async function deleteQuerySession(sessionId: string): Promise<void> {
  const accessToken = await getAccessToken();
  const response = await fetch(
    `${API_BASE_URL}/api/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("登录已失效，请重新登录");
    }
    if (response.status === 403) {
      throw new Error("没有执行该操作的权限");
    }
    throw new Error(`会话删除失败：HTTP ${response.status}`);
  }
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

function ensureStreamResponse(response: Response, action: string): asserts response is Response {
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("登录已失效，请重新登录");
    }
    if (response.status === 403) {
      throw new Error("没有执行该操作的权限");
    }
    if (response.status === 409) {
      throw new Error("查询事件已断档，无法恢复本次查询");
    }
    if (response.status === 404) {
      throw new Error("查询事件已过期，无法恢复本次查询");
    }
    throw new Error(`${action}：HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error("浏览器未返回可读取的流式响应。");
  }
}

async function consumeSseResponse(response: Response, options: QueryOptions) {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let cancelPromise: Promise<void> | undefined;
  const cancelReader = () => {
    cancelPromise ??= reader.cancel().catch(() => undefined);
  };
  options.signal?.addEventListener("abort", cancelReader, { once: true });

  const consumeChunk = (chunk: string) => {
    const parsed = parseSseChunk(chunk);
    if (parsed.eventId) {
      options.onEventId?.(parsed.eventId);
    }
    if (parsed.event) {
      options.onEvent(parsed.event);
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split(/\n\n/);
      buffer = chunks.pop() ?? "";

      for (const chunk of chunks) {
        consumeChunk(chunk);
      }
    }

    if (options.signal?.aborted) {
      throw new DOMException("The operation was aborted.", "AbortError");
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      consumeChunk(buffer);
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

function parseSseChunk(chunk: string): {
  event: AgentEvent | null;
  eventId: string | null;
} {
  const eventId =
    chunk
      .split("\n")
      .find((line) => line.startsWith("id:"))
      ?.replace(/^id:\s?/, "")
      .trim() || null;
  const payload = chunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace(/^data:\s?/, ""))
    .join("\n")
    .trim();

  if (!payload) return { event: null, eventId };

  try {
    return { event: JSON.parse(payload) as AgentEvent, eventId };
  } catch {
    return {
      event: {
        type: "error",
        code: "sse_parse_error",
        message: `无法解析后端事件：${payload}`,
        retryable: false,
      },
      eventId,
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
    can_manage_semantic_model: boolean;
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
        const safeMessage = safeUserManagementMessage(message);
        const error = new Error(safeMessage ?? "操作未完成，请稍后重试。") as Error & {
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
    );
}

export async function getApplicationUser(userId: string): Promise<ApplicationUserDetailResponse> {
    const accessToken = await getAccessToken();
    return getUserManagementJson<ApplicationUserDetailResponse>(
        `/api/admin/users/${encodeURIComponent(userId)}`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
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
    );
}

export type SemanticMemberListResponse = {
    items: SemanticMemberSummary[];
    total: number;
};

export type SemanticReleaseListResponse = {
    items: SemanticRelease[];
    total: number;
};

export type SemanticDraftPayload = {
    release_version: string;
    cubes: SemanticSnapshot["cubes"];
    joins: SemanticSnapshot["joins"];
    members: SemanticMember[];
    reason: string;
};

export type SemanticReviewPayload = {
    decision: "approved" | "rejected";
    reason: string;
};

export type SemanticActionPayload = { reason: string };

async function getSemanticModelJson<T>(
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
            // 非 JSON 错误由状态码处理。
        }
        const error = new Error(message ?? action) as Error & {
            status: number;
            code?: string;
        };
        error.status = response.status;
        if (code && /^[a-z][a-z0-9_]{0,63}$/.test(code)) error.code = code;
        throw error;
    }
    return (await response.json()) as T;
}

async function semanticHeaders(json = false): Promise<HeadersInit> {
    const accessToken = await getAccessToken();
    return {
        Authorization: `Bearer ${accessToken}`,
        ...(json ? { "Content-Type": "application/json" } : {}),
    };
}

function withIdempotency(headers: HeadersInit): HeadersInit {
    return { ...headers, "Idempotency-Key": crypto.randomUUID() };
}

export async function listSemanticMembers(
    memberType: "all" | "measure" | "dimension" | "time_dimension" = "all",
    query = "",
): Promise<SemanticMemberListResponse> {
    const params = new URLSearchParams({ member_type: memberType });
    if (query.trim()) params.set("q", query.trim());
    return getSemanticModelJson<SemanticMemberListResponse>(
        `/api/admin/semantic-model/members?${params.toString()}`,
        { headers: await semanticHeaders() },
        "指标列表加载失败",
    );
}

export async function getSemanticDraft(draftId: string): Promise<SemanticDraft> {
    return getSemanticModelJson<SemanticDraft>(
        `/api/admin/semantic-model/drafts/${encodeURIComponent(draftId)}`,
        { headers: await semanticHeaders() },
        "语义模型草稿加载失败",
    );
}

export async function getSemanticRelease(releaseVersion: string): Promise<SemanticRelease> {
    return getSemanticModelJson<SemanticRelease>(
        `/api/admin/semantic-model/releases/${encodeURIComponent(releaseVersion)}`,
        { headers: await semanticHeaders() },
        "发布版本加载失败",
    );
}

export async function listSemanticReleases(): Promise<SemanticReleaseListResponse> {
    return getSemanticModelJson<SemanticReleaseListResponse>(
        "/api/admin/semantic-model/releases",
        { headers: await semanticHeaders() },
        "发布记录加载失败",
    );
}

export async function createSemanticDraft(payload: SemanticDraftPayload): Promise<SemanticOperation> {
    return getSemanticModelJson<SemanticOperation>(
        "/api/admin/semantic-model/drafts",
        {
            method: "POST",
            headers: withIdempotency(await semanticHeaders(true)),
            body: JSON.stringify(payload),
        },
        "创建语义模型草稿失败",
    );
}

export async function updateSemanticDraft(
    draftId: string,
    payload: SemanticDraftPayload,
): Promise<SemanticOperation> {
    return getSemanticModelJson<SemanticOperation>(
        `/api/admin/semantic-model/drafts/${encodeURIComponent(draftId)}`,
        {
            method: "PUT",
            headers: withIdempotency(await semanticHeaders(true)),
            body: JSON.stringify(payload),
        },
        "保存语义模型草稿失败",
    );
}

export async function validateSemanticDraft(draftId: string): Promise<SemanticOperation> {
    return getSemanticModelJson<SemanticOperation>(
        `/api/admin/semantic-model/drafts/${encodeURIComponent(draftId)}/validate`,
        { method: "POST", headers: await semanticHeaders() },
        "校验语义模型失败",
    );
}

export async function submitSemanticDraft(
    draftId: string,
    payload: SemanticActionPayload,
): Promise<SemanticOperation> {
    return getSemanticModelJson<SemanticOperation>(
        `/api/admin/semantic-model/drafts/${encodeURIComponent(draftId)}/submit`,
        {
            method: "POST",
            headers: withIdempotency(await semanticHeaders(true)),
            body: JSON.stringify(payload),
        },
        "提交语义模型失败",
    );
}

export async function reviewSemanticDraft(
    draftId: string,
    payload: SemanticReviewPayload,
): Promise<SemanticOperation> {
    return getSemanticModelJson<SemanticOperation>(
        `/api/admin/semantic-model/drafts/${encodeURIComponent(draftId)}/review`,
        {
            method: "POST",
            headers: withIdempotency(await semanticHeaders(true)),
            body: JSON.stringify(payload),
        },
        "审核语义模型失败",
    );
}

export async function publishSemanticDraft(
    draftId: string,
    payload: SemanticActionPayload,
): Promise<SemanticOperation> {
    return getSemanticModelJson<SemanticOperation>(
        `/api/admin/semantic-model/drafts/${encodeURIComponent(draftId)}/publish`,
        {
            method: "POST",
            headers: withIdempotency(await semanticHeaders(true)),
            body: JSON.stringify(payload),
        },
        "发布语义模型失败",
    );
}

export async function rollbackSemanticRelease(
    releaseVersion: string,
    payload: SemanticActionPayload,
): Promise<SemanticOperation> {
    return getSemanticModelJson<SemanticOperation>(
        `/api/admin/semantic-model/releases/${encodeURIComponent(releaseVersion)}/rollback`,
        {
            method: "POST",
            headers: withIdempotency(await semanticHeaders(true)),
            body: JSON.stringify(payload),
        },
        "回滚语义模型失败",
    );
}
