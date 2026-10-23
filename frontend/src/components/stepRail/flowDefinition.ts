import type { ProgressStatus } from "../../types/agent";

export type FlowStatus = ProgressStatus | "pending";
export type FlowLane = "shared" | "metric" | "graph" | "sql" | "outcome";

export type FlowNodeId =
  | "conversation"
  | "keywords"
  | "intent"
  | "recall-column"
  | "recall-value"
  | "recall-cube"
  | "kg-recall"
  | "merge"
  | "route"
  | "metric-query"
  | "metric-validate"
  | "cube-execute"
  | "metric-result"
  | "graph-answer"
  | "graph-result"
  | "sql-security"
  | "schema-size"
  | "schema-selector"
  | "apply-selector"
  | "extra-context"
  | "generate-sql"
  | "validate-sql"
  | "correct-sql"
  | "estimate-sql"
  | "run-sql"
  | "sql-result"
  | "clarification"
  | "error";

export type FlowNodeDefinition = {
  id: FlowNodeId;
  lane: FlowLane;
  label: string;
  stepNames?: readonly string[];
  x: number;
  y: number;
  width: number;
};

export type FlowConnector = {
  id: string;
  path: string;
  kind?: "normal" | "branch" | "loop";
  label?: string;
  labelX?: number;
  labelY?: number;
};

export const FLOW_NODES: readonly FlowNodeDefinition[] = [
  {
    id: "conversation",
    lane: "shared",
    label: "解析会话上下文",
    stepNames: ["解析会话上下文"],
    x: 80,
    y: 54,
    width: 150,
  },
  {
    id: "keywords",
    lane: "shared",
    label: "抽取关键词",
    stepNames: ["抽取关键词"],
    x: 238,
    y: 54,
    width: 128,
  },
  {
    id: "intent",
    lane: "shared",
    label: "识别查询意图",
    stepNames: ["识别查询意图"],
    x: 384,
    y: 54,
    width: 140,
  },
  {
    id: "recall-column",
    lane: "shared",
    label: "召回字段",
    stepNames: ["召回字段信息"],
    x: 540,
    y: 54,
    width: 140,
  },
  {
    id: "recall-value",
    lane: "shared",
    label: "召回值域",
    stepNames: ["召回字段取值"],
    x: 540,
    y: 112,
    width: 140,
  },
  {
    id: "recall-cube",
    lane: "shared",
    label: "召回 Cube 成员",
    stepNames: ["召回 Cube 成员"],
    x: 540,
    y: 170,
    width: 156,
  },
  {
    id: "kg-recall",
    lane: "shared",
    label: "知识图谱推理",
    stepNames: ["知识图谱推理"],
    x: 710,
    y: 112,
    width: 150,
  },
  {
    id: "merge",
    lane: "shared",
    label: "合并召回信息",
    stepNames: ["合并召回信息"],
    x: 870,
    y: 112,
    width: 150,
  },
  {
    id: "route",
    lane: "shared",
    label: "语义覆盖判断",
    x: 1052,
    y: 112,
    width: 158,
  },
  {
    id: "metric-query",
    lane: "metric",
    label: "生成 Metric Query",
    stepNames: ["生成 Metric Query"],
    x: 126,
    y: 298,
    width: 168,
  },
  {
    id: "metric-validate",
    lane: "metric",
    label: "校验 Metric Query",
    x: 318,
    y: 298,
    width: 168,
  },
  {
    id: "cube-execute",
    lane: "metric",
    label: "Cube 执行",
    stepNames: ["执行指标查询"],
    x: 510,
    y: 298,
    width: 142,
  },
  {
    id: "metric-result",
    lane: "outcome",
    label: "已验证结果",
    x: 690,
    y: 298,
    width: 142,
  },
  {
    id: "graph-answer",
    lane: "graph",
    label: "返回业务关系",
    stepNames: ["返回业务关系"],
    x: 850,
    y: 394,
    width: 150,
  },
  {
    id: "graph-result",
    lane: "outcome",
    label: "业务关系结果",
    x: 1030,
    y: 394,
    width: 156,
  },
  {
    id: "sql-security",
    lane: "sql",
    label: "SQL 安全检查",
    stepNames: ["SQL 安全检查"],
    x: 126,
    y: 474,
    width: 156,
  },
  {
    id: "schema-size",
    lane: "sql",
    label: "评估 Schema 规模",
    stepNames: ["评估Schema规模"],
    x: 302,
    y: 474,
    width: 168,
  },
  {
    id: "schema-selector",
    lane: "sql",
    label: "Schema Selector",
    stepNames: ["Schema Selector"],
    x: 490,
    y: 430,
    width: 156,
  },
  {
    id: "apply-selector",
    lane: "sql",
    label: "应用 Schema 筛选",
    stepNames: ["应用Schema筛选"],
    x: 490,
    y: 518,
    width: 168,
  },
  {
    id: "extra-context",
    lane: "sql",
    label: "补充上下文",
    stepNames: ["添加额外上下文"],
    x: 676,
    y: 474,
    width: 142,
  },
  {
    id: "generate-sql",
    lane: "sql",
    label: "生成 SQL",
    stepNames: ["生成SQL"],
    x: 836,
    y: 474,
    width: 132,
  },
  {
    id: "validate-sql",
    lane: "sql",
    label: "校验 SQL",
    stepNames: ["校验SQL"],
    x: 988,
    y: 474,
    width: 132,
  },
  {
    id: "correct-sql",
    lane: "sql",
    label: "校正 SQL",
    stepNames: ["校正SQL"],
    x: 988,
    y: 548,
    width: 132,
  },
  {
    id: "estimate-sql",
    lane: "sql",
    label: "评估 SQL 成本",
    stepNames: ["评估SQL成本"],
    x: 836,
    y: 606,
    width: 156,
  },
  {
    id: "run-sql",
    lane: "sql",
    label: "执行 SQL",
    stepNames: ["执行SQL"],
    x: 1016,
    y: 606,
    width: 132,
  },
  {
    id: "sql-result",
    lane: "outcome",
    label: "未验证结果",
    x: 1016,
    y: 680,
    width: 142,
  },
  {
    id: "clarification",
    lane: "outcome",
    label: "需要补充上下文",
    stepNames: ["澄清会话上下文"],
    x: 1184,
    y: 178,
    width: 160,
  },
  {
    id: "error",
    lane: "outcome",
    label: "查询失败",
    x: 1184,
    y: 178,
    width: 160,
  },
];

export const FLOW_CONNECTORS: readonly FlowConnector[] = [
  { id: "conversation-keywords", path: "M155 76 H170", kind: "normal" },
  { id: "keywords-intent", path: "M302 76 H312", kind: "normal" },
  { id: "intent-recall", path: "M454 76 H468", kind: "normal" },
  { id: "recall-column-kg", path: "M610 76 H622 V128 H633", kind: "normal" },
  { id: "recall-value-kg", path: "M610 134 H633", kind: "normal" },
  { id: "recall-cube-kg", path: "M618 192 H628 V140 H633", kind: "normal" },
  { id: "kg-merge", path: "M785 134 H793", kind: "normal" },
  { id: "merge-route", path: "M945 134 H971", kind: "normal" },
  {
    id: "kg-graph-answer",
    path: "M710 156 V240 H850 V394",
    kind: "branch",
    label: "纯关系查询",
    labelX: 718,
    labelY: 232,
  },
  { id: "graph-answer-result", path: "M925 416 H950", kind: "normal" },
  {
    id: "route-metric",
    path: "M1052 156 V276 H126 V298",
    kind: "branch",
    label: "命中受治理指标",
    labelX: 280,
    labelY: 226,
  },
  {
    id: "route-sql",
    path: "M1052 156 V452 H126 V474",
    kind: "branch",
    label: "语义未覆盖且允许 SQL fallback",
    labelX: 140,
    labelY: 440,
  },
  { id: "metric-query-validate", path: "M210 320 H234", kind: "normal" },
  { id: "metric-validate-cube", path: "M402 320 H439", kind: "normal" },
  { id: "cube-result", path: "M581 320 H619", kind: "normal" },
  { id: "schema-security-size", path: "M204 496 H218", kind: "normal" },
  { id: "schema-size-extra", path: "M386 496 H605", kind: "branch" },
  {
    id: "schema-size-selector",
    path: "M386 496 H412 V474 H490",
    kind: "branch",
    label: "大 Schema",
    labelX: 402,
    labelY: 482,
  },
  { id: "selector-apply", path: "M490 474 V518", kind: "normal" },
  { id: "apply-extra", path: "M574 540 H590 V496 H605", kind: "normal" },
  { id: "extra-generate", path: "M747 496 H770", kind: "normal" },
  { id: "generate-validate", path: "M902 496 H922", kind: "normal" },
  {
    id: "validate-estimate",
    path: "M1054 496 V584 H836 V606",
    kind: "branch",
    label: "校验通过",
    labelX: 1064,
    labelY: 568,
  },
  {
    id: "validate-correct",
    path: "M1054 496 V538 H988 V548",
    kind: "branch",
    label: "可修正错误",
    labelX: 1068,
    labelY: 532,
  },
  {
    id: "correct-validate",
    path: "M922 570 H900 V452 H922 V496",
    kind: "loop",
    label: "重新校验",
    labelX: 842,
    labelY: 444,
  },
  { id: "estimate-run", path: "M914 628 H950", kind: "normal" },
  { id: "run-result", path: "M1016 650 V680", kind: "normal" },
  {
    id: "clarification-end",
    path: "M1052 156 V200 H1102",
    kind: "branch",
    label: "需要澄清",
    labelX: 1058,
    labelY: 170,
  },
  {
    id: "error-end",
    path: "M1052 156 V200 H1102",
    kind: "branch",
    label: "执行失败",
    labelX: 1058,
    labelY: 190,
  },
];
