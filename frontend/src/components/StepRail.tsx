/**
 * 智能体执行流程图组件
 * 按 LangGraph 节点拓扑展示各步骤状态，随分析过程展开后直接平铺
 * running 节点朱砂脉冲，流式期间连接线虚线流动
 */
import { Check, Circle, LoaderCircle, X } from "lucide-react";
import { cn } from "../lib/format";
import type { ProgressStatus, StepState } from "../types/agent";

type FlowStatus = ProgressStatus | "pending";

type FlowNode = {
    step: string;
    x: number;
    y: number;
    w?: number;
};

const nodes: FlowNode[] = [
    { step: "抽取关键词", x: 410, y: 20 },
    { step: "召回字段信息", x: 150, y: 112 },
    { step: "召回指标信息", x: 410, y: 112 },
    { step: "召回字段取值", x: 670, y: 112 },
    { step: "合并召回信息", x: 410, y: 214 },
    { step: "过滤指标信息", x: 290, y: 318 },
    { step: "过滤表信息", x: 530, y: 318 },
    { step: "增加额外上下文", x: 410, y: 422, w: 176 },
    { step: "生成SQL", x: 410, y: 526 },
    { step: "校验SQL", x: 410, y: 630 },
    { step: "校正SQL", x: 670, y: 630 },
    { step: "执行SQL", x: 410, y: 724 },
];

const connectors = [
    "M410 60 L410 84 L150 84 L150 106",
    "M410 60 L410 106",
    "M410 60 L410 84 L670 84 L670 106",
    "M150 152 L150 178 L410 178 L410 208",
    "M410 152 L410 208",
    "M670 152 L670 178 L410 178 L410 208",
    "M410 254 L410 282 L290 282 L290 312",
    "M410 254 L410 282 L530 282 L530 312",
    "M290 358 L290 386 L410 386 L410 416",
    "M530 358 L530 386 L410 386 L410 416",
    "M410 462 L410 520",
    "M410 566 L410 624",
    "M410 670 L410 718",
    "M488 650 L586 650",
    "M670 670 L670 696 L410 696 L410 718",
];

const branchLabels = [
    { text: "有误", x: 530, y: 642 },
    { text: "无误", x: 366, y: 704 },
];

function getStatusMap(steps: StepState[]) {
    return steps.reduce<Record<string, StepState>>((map, item) => {
        map[item.step] = item;
        return map;
    }, {});
}

function statusFor(step: string, map: Record<string, StepState>): FlowStatus {
    return map[step]?.status ?? "pending";
}

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

function FlowNodeCard({ node, status }: { node: FlowNode; status: FlowStatus }) {
    const width = node.w ?? 156;

    return (
        <div
            className="absolute -translate-x-1/2"
            style={{ left: node.x, top: node.y, width }}
        >
            <div
                className={cn(
                    "flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-semibold shadow-line transition",
                    status === "pending" && "border-ink/10 bg-white/60 text-ink/45",
                    status === "running" && "node-running border-cinnabar/50 bg-cinnabar/10 text-ink",
                    status === "success" && "border-pine/30 bg-pine/10 text-ink",
                    status === "error" && "border-oxide/35 bg-oxide/10 text-oxide",
                )}
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
                <span className="min-w-0 flex-1 truncate">{node.step}</span>
            </div>
        </div>
    );
}

export function StepRail({ steps = [] }: { steps?: StepState[] }) {
    const runningStep = steps.find((item) => item.status === "running")?.step ?? null;
    const errorCount = steps.filter((item) => item.status === "error").length;
    const doneCount = steps.filter((item) => item.status === "success").length;

    if (steps.length === 0) return null;

    const statusMap = getStatusMap(steps);

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
                    {runningStep
                        ? `正在执行：${runningStep}`
                        : errorCount > 0
                          ? `${errorCount} 个节点失败`
                          : `已执行 ${doneCount} 步`}
                </span>
                <span className="hidden shrink-0 text-xs text-ink/40 sm:inline">LangGraph</span>
            </div>

            <div className="mt-3 overflow-x-auto">
                <div className="relative mx-auto h-[780px] w-[820px]">
                    <svg
                        className="pointer-events-none absolute inset-0 h-full w-full"
                        viewBox="0 0 820 780"
                        fill="none"
                        aria-hidden="true"
                    >
                        <defs>
                            <marker
                                id="flow-arrow"
                                markerHeight="8"
                                markerWidth="8"
                                orient="auto"
                                refX="6"
                                refY="4"
                            >
                                <path d="M0 0 L8 4 L0 8 Z" fill="rgba(33,44,62,0.55)" />
                            </marker>
                        </defs>
                        <g className={runningStep ? "flow-live" : undefined}>
                            {connectors.map((path) => (
                                <path
                                    key={path}
                                    d={path}
                                    stroke="rgba(33,44,62,0.45)"
                                    strokeWidth="1.5"
                                    strokeDasharray="4 4"
                                    markerEnd="url(#flow-arrow)"
                                />
                            ))}
                        </g>
                        {branchLabels.map((label) => (
                            <text
                                key={label.text}
                                x={label.x}
                                y={label.y}
                                fill="rgba(33,44,62,0.6)"
                                fontSize="13"
                                fontWeight="600"
                            >
                                {label.text}
                            </text>
                        ))}
                    </svg>

                    {nodes.map((node) => (
                        <FlowNodeCard
                            key={node.step}
                            node={node}
                            status={statusFor(node.step, statusMap)}
                        />
                    ))}
                </div>
            </div>
        </section>
    );
}
