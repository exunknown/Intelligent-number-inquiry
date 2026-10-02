/**
 * 智能体类型定义
 * 定义问数智能体前端使用的 SSE 事件、流程步骤和聊天消息类型
 */
export type ProgressStatus = "running" | "success" | "error";

export type ProgressEvent = {
  type: "progress";
  step: string;
  status: ProgressStatus;
};

export type MetricDisplayEntry = {
  member_id: string;
  title: string;
  role?: "primary" | "attached";
  source_member_id?: string | null;
};

export type MetricItem = string | MetricDisplayEntry;

export type MetricsEvent = {
  type: "metrics";
  data: MetricItem[];
};

export type QueryMode = "metric" | "sql";

export type RouteEvent = {
  type: "route";
  mode: QueryMode;
  reason: string;
};

export type ResultEvent = {
  type: "result";
  data: unknown;
  source: QueryMode;
  verified: boolean;
  warning: string | null;
  row_count?: number;
  truncated?: boolean;
  export_id?: string;
  export_available?: boolean;
  export_expires_at?: string;
};

export type ErrorEvent = {
  type: "error";
  code: string;
  message: string;
  retryable: boolean;
};

export type HeartbeatEvent = {
  type: "heartbeat";
};

export type AgentEvent =
  | ProgressEvent
  | MetricsEvent
  | RouteEvent
  | ResultEvent
  | ErrorEvent
  | HeartbeatEvent;

export type StepState = {
  step: string;
  status: ProgressStatus;
  updatedAt: number;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  status?: "streaming" | "done" | "error" | "cancelled";
  steps?: StepState[];
  metrics?: MetricItem[];
  queryMode?: QueryMode;
  routeReason?: string;
  result?: unknown;
  verified?: boolean;
  warning?: string | null;
  error?: string;
  errorCode?: string;
  retryable?: boolean;
  rowCount?: number;
  truncated?: boolean;
  exportId?: string;
};
