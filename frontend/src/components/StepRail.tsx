/**
 * 智能体执行流程图组件
 * 展示共享语义理解、Metric / SQL 双执行泳道和统一结果终点
 */
import { Check, Circle, LoaderCircle, X } from "lucide-react";
import { cn } from "../lib/format";
import type { ChatMessage, QueryMode, StepState } from "../types/agent";
import {
    FLOW_CONNECTORS,
    FLOW_NODES,
    type FlowConnector,
    type FlowLane,
    type FlowNodeDefinition,
    type FlowStatus,
} from "./stepRail/flowDefinition";
import {
    buildStatusMap,
    getFlowStatus,
    getLaneState,
    getOutcomeState,
    type LaneState,
} from "./stepRail/flowState";

type StepRailProps = {
    steps?: StepState[];
    queryMode?: QueryMode;
    status?: ChatMessage["status"];
    hasResult?: boolean;
    verified?: boolean;
    errorCode?: string;
};

const laneLabels: Record<FlowLane, string> = {
    shared: "共享前置语义理解",
    metric: "Text to Metric · 受治理指标",
    sql: "Text to SQL · 受控 SQL fallback",
    outcome: "统一结果反馈",
};

const metricConnectorIds = new Set([
    "route-metric",
    "metric-query-validate",
    "metric-validate-cube",
    "cube-result",
]);

const sqlConnectorIds = new Set([
    "route-sql",
    "schema-security-size",
    "schema-size-extra",
    "schema-size-selector",
    "selector-apply",
    "apply-extra",
    "extra-generate",
    "generate-validate",
    "validate-estimate",
    "validate-correct",
    "correct-validate",
    "estimate-run",
    "run-result",
]);

function NodeIcon({ status }: { status: FlowStatus }) {
    if (status === "running") {
        return <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />;
    }

    if (status === "success") {
        return <Check className="h-3.5 w-3.5" aria-hidden="true" />;
    }

    if (status === "error") {
        return <X className="h-3.5 w-3.5" aria-hidden="true" />;
    }

    return <Circle className="h-3.5 w-3.5" aria-hidden="true" />;
}

function laneTone(laneState: LaneState) {
    return laneState === "inactive" ? "opacity-45" : "";
}

function FlowNodeCard({
    node,
    status,
    laneState,
}: {
    node: FlowNodeDefinition;
    status: FlowStatus;
    laneState: LaneState;
}) {
    return (
        <div
            className={cn("absolute -translate-x-1/2", laneTone(laneState))}
            style={{ left: node.x, top: node.y, width: node.width }}
        >
            <div
                className={cn(
                    "flex h-11 items-center gap-2 rounded-lg border px-3 text-sm font-semibold shadow-line transition",
                    status === "pending" && "border-ink/10 bg-white/60 text-ink/45",
                    status === "running" && "node-running border-cinnabar/50 bg-cinnabar/10 text-ink",
                    status === "success" && "border-pine/30 bg-pine/10 text-ink",
                    status === "error" && "border-oxide/35 bg-oxide/10 text-oxide",
                )}
                title={node.label}
            >
                <span
                    className={cn(
                        "grid h-6 w-6 shrink-0 place-items-center rounded-full",
                        status === "pending" && "bg-ink/5 text-ink/35",
                        status === "running" && "bg-cinnabar/15 text-cinnabar",
                        status === "success" && "bg-pine/15 text-pine",
                        status === "error" && "bg-oxide/15 text-oxide",
                    )}
                >
                    <NodeIcon status={status} />
                </span>
                <span className="min-w-0 flex-1 truncate">{node.label}</span>
            </div>
        </div>
    );
}

function OutcomeCard({
    node,
    status,
    note,
}: {
    node: FlowNodeDefinition;
    status: FlowStatus;
    note?: string;
}) {
    return (
        <div
            className="absolute -translate-x-1/2"
            style={{ left: node.x, top: node.y, width: node.width }}
        >
            <div
                className={cn(
                    "rounded-lg border px-3 py-2 shadow-line transition",
                    status === "error" && "border-cinnabar/35 bg-cinnabar/10 text-ink",
                    status === "success" && "border-pine/30 bg-pine/10 text-ink",
                    status === "pending" && "border-ink/10 bg-white/60 text-ink/45",
                )}
                title={node.label}
            >
                <div className="flex items-center gap-2 text-sm font-semibold">
                    <span
                        className={cn(
                            "grid h-6 w-6 shrink-0 place-items-center rounded-full",
                            status === "error" && "bg-cinnabar/15 text-cinnabar",
                            status === "success" && "bg-pine/15 text-pine",
                            status === "pending" && "bg-ink/5 text-ink/35",
                        )}
                    >
                        <NodeIcon status={status} />
                    </span>
                    <span className="truncate">{node.label}</span>
                </div>
                {note && <div className="mt-1 pl-8 text-[11px] text-ink/55">{note}</div>}
            </div>
        </div>
    );
}

function laneStateForNode(
    node: FlowNodeDefinition,
    queryMode: QueryMode | undefined,
): LaneState {
    if (node.lane === "outcome") return "active";
    return getLaneState(node.lane, queryMode);
}

function connectorLane(connector: FlowConnector): Exclude<FlowLane, "outcome"> | null {
    if (metricConnectorIds.has(connector.id)) return "metric";
    if (sqlConnectorIds.has(connector.id)) return "sql";
    return null;
}

function connectorClass(
    connector: FlowConnector,
    queryMode: QueryMode | undefined,
    isStreaming: boolean,
) {
    const lane = connectorLane(connector);
    const laneState = lane ? getLaneState(lane, queryMode) : "active";
    return cn(
        laneState === "inactive" && "opacity-25",
        laneState === "unknown" && "opacity-70",
        connector.kind === "loop" && "flow-loop",
        isStreaming && laneState === "active" && lane && "flow-live",
    );
}

function connectorStroke(
    connector: FlowConnector,
    queryMode: QueryMode | undefined,
): string {
    if (connector.kind === "loop") return "rgba(194,65,86,0.68)";
    if (connectorLane(connector) === "metric" && queryMode === "metric") {
        return "rgba(33,133,111,0.72)";
    }
    if (connectorLane(connector) === "sql" && queryMode === "sql") {
        return "rgba(194,65,86,0.72)";
    }
    return "rgba(31,41,55,0.42)";
}

export function StepRail({
    steps = [],
    queryMode,
    status,
    hasResult = false,
    verified = false,
    errorCode,
}: StepRailProps) {
    if (steps.length === 0 && !queryMode && !hasResult && !errorCode) return null;

    const statusMap = buildStatusMap(steps);
    const runningStep = steps.find((item) => item.status === "running");
    const errorCount = steps.filter((item) => item.status === "error").length;
    const doneCount = steps.filter((item) => item.status === "success").length;
    const isStreaming = status === "streaming";
    const outcome = getOutcomeState(queryMode, status, hasResult, verified, errorCode);
    const outcomeNode = outcome
        ? FLOW_NODES.find((node) => node.id === outcome.id)
        : undefined;

    const summary = runningStep
        ? runningStep.message ?? `正在执行：${runningStep.step}`
        : errorCount > 0
          ? `${errorCount} 个节点失败`
          : `已执行 ${doneCount} 步`;

    return (
        <section>
            <div className="flex items-center gap-2.5">
                <span className="shrink-0 font-serif text-sm font-bold text-ink">执行流程</span>
                <span
                    className={cn(
                        "min-w-0 flex-1 truncate text-xs",
                        runningStep && "text-cinnabar",
                        !runningStep && errorCount > 0 && "text-oxide",
                        !runningStep && errorCount === 0 && "text-ink/45",
                    )}
                >
                    {summary}
                </span>
                <span className="hidden shrink-0 text-xs text-ink/40 sm:inline">
                    共享语义 · 双路径
                </span>
            </div>

            <div className="mt-3 overflow-x-auto">
                <div
                    className="relative mx-auto h-[760px] w-[1160px]"
                    aria-label="问数执行流程图"
                    role="img"
                >
                    <div className="absolute left-0 top-4 font-serif text-xs font-bold text-ink/55">
                        {laneLabels.shared}
                    </div>
                    <div className="absolute left-0 top-[258px] font-serif text-xs font-bold text-pine">
                        {laneLabels.metric}
                    </div>
                    <div className="absolute left-0 top-[434px] font-serif text-xs font-bold text-oxide">
                        {laneLabels.sql}
                    </div>
                    <div className="absolute left-[690px] top-[258px] font-serif text-xs font-bold text-pine/75">
                        {laneLabels.outcome}
                    </div>

                    <svg
                        className="pointer-events-none absolute inset-0 h-full w-full"
                        viewBox="0 0 1160 760"
                        fill="none"
                        aria-hidden="true"
                    >
                        <defs>
                            <marker
                                id="step-rail-flow-arrow"
                                markerHeight="8"
                                markerWidth="8"
                                orient="auto"
                                refX="6"
                                refY="4"
                            >
                                <path d="M0 0 L8 4 L0 8 Z" fill="rgba(31,41,55,0.55)" />
                            </marker>
                        </defs>
                        {FLOW_CONNECTORS.map((connector) => (
                            <g key={connector.id} className={connectorClass(connector, queryMode, isStreaming)}>
                                <path
                                    d={connector.path}
                                    stroke={connectorStroke(connector, queryMode)}
                                    strokeWidth={connector.kind === "loop" ? 2 : 1.5}
                                    strokeDasharray={connector.kind === "loop" ? "5 4" : "4 4"}
                                    markerEnd="url(#step-rail-flow-arrow)"
                                />
                                {connector.label && (
                                    <text
                                        x={connector.labelX}
                                        y={connector.labelY}
                                        fill={connector.kind === "loop" ? "rgba(194,65,86,0.8)" : "rgba(31,41,55,0.58)"}
                                        fontSize="12"
                                        fontWeight="600"
                                    >
                                        {connector.label}
                                    </text>
                                )}
                            </g>
                        ))}
                    </svg>

                    {FLOW_NODES.filter((node) => node.id !== "metric-result" && node.id !== "sql-result" && node.id !== "clarification").map(
                        (node) => (
                            <FlowNodeCard
                                key={node.id}
                                node={node}
                                status={getFlowStatus(
                                    node,
                                    statusMap,
                                    queryMode,
                                    status,
                                    hasResult,
                                    verified,
                                )}
                                laneState={laneStateForNode(node, queryMode)}
                            />
                        ),
                    )}

                    {outcome && outcomeNode && (
                        <OutcomeCard
                            node={outcomeNode}
                            status={outcome.status}
                            note={outcome.id === "sql-result" ? "需人工核对" : undefined}
                        />
                    )}

                    {outcome?.id === "error" && (
                        <div className="absolute left-[1016px] top-[680px] w-[142px] -translate-x-1/2">
                            <div className="rounded-lg border border-oxide/35 bg-oxide/10 px-3 py-2 text-sm font-semibold text-oxide shadow-line">
                                <div className="flex items-center gap-2">
                                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-oxide/15">
                                        <X className="h-3.5 w-3.5" aria-hidden="true" />
                                    </span>
                                    <span className="truncate">查询失败</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
}
