import type {
    ChatMessage,
    MetricDisplayEntry,
    ProcessEvent,
    ProgressStatus,
    QueryMode,
    StepState,
} from "../types/agent";
import type {
    QueryMessageResponse,
    QuerySessionAuditMessage,
    QuerySessionDetail,
    QuerySessionMessage,
} from "./agentApi";

function sanitizeMetricItems(value: unknown): ChatMessage["metrics"] {
    if (!Array.isArray(value)) return [];
    return value.flatMap((item): NonNullable<ChatMessage["metrics"]> => {
        if (typeof item === "string") return [item];
        if (!item || typeof item !== "object") return [];
        const candidate = item as Record<string, unknown>;
        if (
            typeof candidate.member_id !== "string" ||
            !candidate.member_id ||
            typeof candidate.title !== "string" ||
            !candidate.title
        ) {
            return [];
        }
        const safe: MetricDisplayEntry = {
            member_id: candidate.member_id,
            title: candidate.title,
        };
        if (candidate.role === "primary" || candidate.role === "attached") {
            safe.role = candidate.role;
        }
        if (
            candidate.source_member_id === null ||
            typeof candidate.source_member_id === "string"
        ) {
            safe.source_member_id = candidate.source_member_id;
        }
        return [safe];
    });
}

function sanitizeMissingRequirements(
    value: unknown,
): ChatMessage["missingRequirements"] {
    if (!Array.isArray(value)) return [];
    const allowedTypes = new Set([
        "metric",
        "dimension",
        "time_range",
        "field",
        "data_scope",
    ]);
    const seenTypes = new Set<string>();
    return value.slice(0, 8).flatMap((item): NonNullable<ChatMessage["missingRequirements"]> => {
        if (!item || typeof item !== "object") return [];
        const candidate = item as Record<string, unknown>;
        if (
            typeof candidate.type !== "string" ||
            !candidate.type ||
            !allowedTypes.has(candidate.type) ||
            seenTypes.has(candidate.type) ||
            typeof candidate.label !== "string" ||
            !candidate.label ||
            typeof candidate.example !== "string" ||
            !candidate.example
        ) {
            return [];
        }
        seenTypes.add(candidate.type);
        return [
            {
                type: candidate.type,
                label: candidate.label.slice(0, 128),
                example: candidate.example.slice(0, 128),
            },
        ];
    });
}

function messageTime(value: string) {
    const parsed = new Date(value).getTime();
    return Number.isFinite(parsed) ? parsed : 0;
}

function queryMode(value: string | null | undefined): QueryMode | undefined {
    return value === "metric" || value === "sql" ? value : undefined;
}

function progressStatus(value: string): ProgressStatus {
    return value === "running" || value === "error" ? value : "success";
}

function hydrateSteps(
    steps: Record<string, string> | null | undefined,
    updatedAt: number,
): StepState[] | undefined {
    if (!steps || Object.keys(steps).length === 0) return undefined;
    return Object.entries(steps).map(([step, status]) => ({
        step,
        status: progressStatus(status),
        updatedAt,
    }));
}

export function hydrateProcessEvents(
    processEvents: QueryMessageResponse["process_events"],
    steps: Record<string, string> | null | undefined,
    createdAt: number,
): ProcessEvent[] | undefined {
    if (processEvents !== null && processEvents !== undefined) {
        if (!Array.isArray(processEvents)) return [];
        return processEvents.flatMap((item): ProcessEvent[] => {
            if (!item || typeof item !== "object") return [];
            const candidate = item as Record<string, unknown>;
            const status = candidate.status;
            const occurredAt = candidate.occurred_at;
            if (
                typeof candidate.step !== "string" ||
                !candidate.step ||
                (status !== "running" && status !== "success" && status !== "error") ||
                typeof occurredAt !== "string"
            ) {
                return [];
            }
            const parsedOccurredAt = messageTime(occurredAt);
            if (!Number.isFinite(parsedOccurredAt)) return [];
            const message = candidate.message;
            if (message !== null && message !== undefined && typeof message !== "string") {
                return [];
            }
            return [{
                step: candidate.step,
                status,
                message: message ?? null,
                occurredAt: parsedOccurredAt,
            }];
        });
    }

    if (!steps || Object.keys(steps).length === 0) return undefined;
    return Object.entries(steps).map(([step, status]) => ({
        step,
        status: progressStatus(status),
        message: null,
        occurredAt: createdAt,
    }));
}

function isQueryMessage(message: QuerySessionMessage): message is QueryMessageResponse {
    return "message_id" in message && "role" in message;
}

function hydrateQueryMessage(message: QueryMessageResponse): ChatMessage {
    const createdAt = messageTime(message.created_at);
    const base: ChatMessage = {
        id: message.message_id,
        role: message.role,
        content: message.content,
        createdAt,
        status:
            message.status === "cancelled"
                ? "cancelled"
                : message.status === "error"
                  ? "error"
                  : message.status === "streaming"
                    ? "streaming"
                    : "done",
    };

    if (message.role === "user") return base;

    return {
        ...base,
        steps: hydrateSteps(message.steps, createdAt),
        processEvents: hydrateProcessEvents(message.process_events, message.steps, createdAt),
        metrics: message.metrics ? sanitizeMetricItems(message.metrics) : undefined,
        queryMode: queryMode(message.query_mode),
        routeReason: message.route_reason ?? undefined,
        ...(message.result_preview !== null && message.result_preview !== undefined
            ? { result: message.result_preview }
            : {}),
        verified: message.verified ?? undefined,
        warning: message.warning,
        error: message.error ?? undefined,
        errorCode: message.error_code ?? undefined,
        retryable: message.retryable ?? undefined,
        missingRequirements: sanitizeMissingRequirements(message.missing_requirements),
        rowCount: message.row_count ?? undefined,
        truncated: message.truncated ?? undefined,
        exportId: message.export_id ?? undefined,
    };
}

function legacyAssistantContent(message: QuerySessionAuditMessage) {
    if (message.outcome === "success") {
        return message.result_row_count === 0
            ? "查询完成，结果为空。"
            : `查询完成，共返回 ${message.result_row_count ?? 0} 行结果。`;
    }
    if (message.outcome === "cancelled") return "已停止本次查询。";
    return "这次查询没有成功。";
}

function hydrateLegacyMessage(
    message: QuerySessionAuditMessage,
    index: number,
): [ChatMessage, ChatMessage] {
    const requestId = message.request_id ?? `legacy-${index}`;
    const createdAt = messageTime(message.created_at);
    const assistantStatus =
        message.outcome === "success"
            ? "done"
            : message.outcome === "cancelled"
              ? "cancelled"
              : "error";

    return [
        {
            id: `${requestId}:user`,
            role: "user",
            content: message.query_text,
            createdAt,
        },
        {
            id: `${requestId}:assistant`,
            role: "assistant",
            content: legacyAssistantContent(message),
            createdAt,
            status: assistantStatus,
            queryMode: queryMode(message.query_mode),
            routeReason: message.route_reason ?? undefined,
            verified: message.verified ?? undefined,
            errorCode: message.error_code ?? undefined,
            rowCount: message.result_row_count ?? undefined,
            truncated: message.result_truncated ?? undefined,
        },
    ];
}

export function hydrateSessionMessages(detail: QuerySessionDetail): ChatMessage[] {
    const messages = [...detail.messages].sort((left, right) => {
        if (isQueryMessage(left) && isQueryMessage(right)) {
            return left.sequence_no - right.sequence_no;
        }
        return messageTime(left.created_at) - messageTime(right.created_at);
    });

    if (messages.length === 0) return [];
    if (messages.every(isQueryMessage)) {
        return messages.map(hydrateQueryMessage);
    }

    return messages.flatMap((message, index) =>
        isQueryMessage(message) ? [hydrateQueryMessage(message)] : hydrateLegacyMessage(message, index),
    );
}
