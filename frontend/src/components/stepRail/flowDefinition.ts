import type { ProgressStatus } from "../../types/agent";

export type FlowStatus = ProgressStatus | "pending";
export type FlowLane = "shared" | "metric" | "sql" | "outcome";

export type FlowNodeId =
  | "conversation"
  | "keywords"
  | "recall-column"
  | "recall-value"
  | "recall-cube"
  | "merge"
  | "route"
  | "metric-query"
  | "metric-validate"
  | "cube-execute"
  | "metric-result"
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
  | "clarification";

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
    x: 82,
    y: 54,
    width: 156,
  },
  {
    id: "keywords",
    lane: "shared",
    label: "抽取关键词",
    stepNames: ["抽取关键词"],
    x: 262,
    y: 54,
    width: 140,
  },
  {
    id: "recall-column",
    lane: "shared",
    label: "召回字段",
    stepNames: ["召回字段信息"],
    x: 430,
    y: 54,
    width: 132,
  },
  {
    id: "recall-value",
    lane: "shared",
    label: "召回值域",
    stepNames: ["召回字段取值"],
    x: 430,
    y: 112,
    width: 132,
  },
  {
    id: "recall-cube",
    lane: "shared",
    label: "召回 Cube 成员",
    stepNames: ["召回 Cube 成员"],
    x: 430,
    y: 170,
    width: 156,
  },
  {
    id: "merge",
    lane: "shared",
    label: "合并召回信息",
    stepNames: ["合并召回信息"],
    x: 628,
    y: 112,
    width: 156,
  },
  {
    id: "route",
    lane: "shared",
    label: "语义覆盖判断",
    x: 820,
    y: 112,
    width: 156,
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
    x: 1000,
    y: 178,
    width: 168,
  },
];

export const FLOW_CONNECTORS: readonly FlowConnector[] = [
  { id: "conversation-keywords", path: "M160 74 H192", kind: "normal" },
  { id: "keywords-recall", path: "M332 74 H370", kind: "normal" },
  { id: "recall-column-merge", path: "M496 74 H560 V132 H550", kind: "normal" },
  { id: "recall-value-merge", path: "M496 132 H550", kind: "normal" },
  { id: "recall-cube-merge", path: "M496 190 H560 V132 H550", kind: "normal" },
  { id: "merge-route", path: "M706 132 H742", kind: "normal" },
  {
    id: "route-metric",
    path: "M820 152 V238 H210 V288",
    kind: "branch",
    label: "命中受治理指标",
    labelX: 280,
    labelY: 226,
  },
  {
    id: "route-sql",
    path: "M898 152 V414 H126 V464",
    kind: "branch",
    label: "语义未覆盖且允许 SQL fallback",
    labelX: 720,
    labelY: 402,
  },
  { id: "metric-query-validate", path: "M294 318 H308", kind: "normal" },
  { id: "metric-validate-cube", path: "M486 318 H500", kind: "normal" },
  { id: "cube-result", path: "M652 318 H680", kind: "normal" },
  { id: "schema-security-size", path: "M282 494 H294", kind: "normal" },
  { id: "schema-size-extra", path: "M470 494 H610 V494 H666", kind: "branch" },
  {
    id: "schema-size-selector",
    path: "M386 464 V422 H480",
    kind: "branch",
    label: "大 Schema",
    labelX: 402,
    labelY: 446,
  },
  { id: "selector-apply", path: "M568 470 V508", kind: "normal" },
  { id: "apply-extra", path: "M658 538 H666 V494", kind: "normal" },
  { id: "extra-generate", path: "M818 494 H826", kind: "normal" },
  { id: "generate-validate", path: "M968 494 H978", kind: "normal" },
  {
    id: "validate-estimate",
    path: "M1054 494 V596 H826",
    kind: "branch",
    label: "校验通过",
    labelX: 1064,
    labelY: 562,
  },
  {
    id: "validate-correct",
    path: "M1054 514 V538 H978",
    kind: "branch",
    label: "可修正错误",
    labelX: 1068,
    labelY: 532,
  },
  {
    id: "correct-validate",
    path: "M978 568 H944 V452 H1054 V464",
    kind: "loop",
    label: "重新校验",
    labelX: 914,
    labelY: 444,
  },
  { id: "estimate-run", path: "M992 630 H1006", kind: "normal" },
  { id: "run-result", path: "M1082 650 V670", kind: "normal" },
  {
    id: "clarification-end",
    path: "M898 152 V178 H990",
    kind: "branch",
    label: "需要澄清",
    labelX: 916,
    labelY: 170,
  },
];
