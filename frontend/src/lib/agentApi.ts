/**
 * 智能体接口客户端
 * 封装后端 /api/query SSE 流式接口请求与事件解析逻辑
 */
import { getAccessToken } from "../auth/keycloak";
import type { AgentEvent } from "../types/agent";

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

  buffer += decoder.decode();
  const tail = parseSseChunk(buffer);
  if (tail) {
    options.onEvent(tail);
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
