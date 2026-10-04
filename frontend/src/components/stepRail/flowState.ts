import type { ChatMessage, QueryMode, StepState } from "../../types/agent";
import type {
  FlowLane,
  FlowNodeDefinition,
  FlowNodeId,
  FlowStatus,
} from "./flowDefinition";

export type LaneState = "active" | "inactive" | "unknown";

export type OutcomeState = {
  id: "metric-result" | "sql-result" | "clarification" | "error";
  status: FlowStatus;
  label: string;
};

export function buildStatusMap(
  steps: readonly StepState[],
): ReadonlyMap<string, StepState> {
  const statusMap = new Map<string, StepState>();
  for (const step of steps) {
    const current = statusMap.get(step.step);
    if (!current || step.updatedAt >= current.updatedAt) {
      statusMap.set(step.step, step);
    }
  }
  return statusMap;
}

function getStepStatus(
  node: FlowNodeDefinition,
  statusMap: ReadonlyMap<string, StepState>,
): FlowStatus {
  if (!node.stepNames) {
    return "pending";
  }

  let latest: StepState | undefined;
  for (const stepName of node.stepNames) {
    const step = statusMap.get(stepName);
    if (step && (!latest || step.updatedAt >= latest.updatedAt)) {
      latest = step;
    }
  }
  return latest?.status ?? "pending";
}

export function getFlowStatus(
  node: FlowNodeDefinition,
  statusMap: ReadonlyMap<string, StepState>,
  queryMode?: QueryMode,
  messageStatus?: ChatMessage["status"],
  hasResult = false,
  verified = false,
): FlowStatus {
  if (node.id === "route") {
    return queryMode ? "success" : "pending";
  }

  if (node.id === "metric-validate") {
    const metricQueryStatus = statusMap.get("生成 Metric Query")?.status;
    if (metricQueryStatus === "error") {
      return "error";
    }
    return metricQueryStatus === "success" && queryMode ? "success" : "pending";
  }

  if (node.id === "metric-result") {
    return hasResult && queryMode === "metric" && verified ? "success" : "pending";
  }

  if (node.id === "sql-result") {
    return hasResult && queryMode === "sql" && messageStatus === "done"
      ? "success"
      : "pending";
  }

  return getStepStatus(node, statusMap);
}

export function getLaneState(
  lane: Exclude<FlowLane, "outcome">,
  queryMode?: QueryMode,
): LaneState {
  if (!queryMode) {
    return "unknown";
  }
  if (lane === "shared") {
    return "active";
  }
  return lane === queryMode ? "active" : "inactive";
}

export function getOutcomeState(
  queryMode: QueryMode | undefined,
  messageStatus: ChatMessage["status"] | undefined,
  hasResult: boolean,
  verified = false,
  errorCode?: string,
): OutcomeState | null {
  if (messageStatus === "error") {
    if (errorCode === "conversation_clarification_required") {
      return {
        id: "clarification",
        status: "error",
        label: "需要补充上下文",
      };
    }
    return { id: "error", status: "error", label: "查询失败" };
  }

  if (!hasResult || messageStatus !== "done") {
    return null;
  }

  if (queryMode === "metric" && verified) {
    return { id: "metric-result", status: "success", label: "已验证结果" };
  }
  if (queryMode === "metric") {
    return { id: "metric-result", status: "success", label: "未验证结果" };
  }
  if (queryMode === "sql") {
    return { id: "sql-result", status: "success", label: "未验证结果" };
  }
  return null;
}

export type FlowNodeStatus = Readonly<Record<FlowNodeId, FlowStatus>>;
