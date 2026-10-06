export const KNOWLEDGE_GRAPH_NODE_TYPES = [
    "table",
    "column",
    "cube",
    "semantic_member",
    "metric_equivalence_group",
    "business_term",
    "value",
] as const;

export const BUSINESS_KNOWLEDGE_GRAPH_NODE_TYPES = [
    "customer_segment",
    "customer",
    "product",
    "category",
    "brand",
    "region",
    "metric",
    "time_period",
] as const;

export const KNOWLEDGE_GRAPH_VIEWS = ["relation", "schema"] as const;
export const KNOWLEDGE_GRAPH_SCENARIOS = ["product", "customer", "region", "metric"] as const;

export type TechnicalKnowledgeGraphNodeType = (typeof KNOWLEDGE_GRAPH_NODE_TYPES)[number];
export type BusinessKnowledgeGraphNodeType = (typeof BUSINESS_KNOWLEDGE_GRAPH_NODE_TYPES)[number];
export type KnowledgeGraphNodeType = TechnicalKnowledgeGraphNodeType | BusinessKnowledgeGraphNodeType;
export type KnowledgeGraphView = (typeof KNOWLEDGE_GRAPH_VIEWS)[number];
export type KnowledgeGraphScenario = (typeof KNOWLEDGE_GRAPH_SCENARIOS)[number];

export type KnowledgeGraphNode = {
    node_id: string;
    node_type: KnowledgeGraphNodeType;
    title: string;
    description: string;
    metadata: Record<string, unknown>;
    source: string;
    confidence: number;
    release_version: string;
};

export type KnowledgeGraphEdge = {
    edge_id: string;
    source_node_id: string;
    target_node_id: string;
    edge_type: string;
    weight: number;
    source: string;
    release_version: string;
};

export type KnowledgeGraphPath = {
    node_ids: string[];
    edge_ids: string[];
    score: number;
};

export type KnowledgeGraphRelease = {
    release_version: string;
    status: string;
    active: boolean;
    created_at: string | null;
    node_count: number;
    edge_count: number;
};

export type KnowledgeGraphReleaseListResponse = {
    items: KnowledgeGraphRelease[];
    active_release_version: string | null;
    backend: "mysql" | "neo4j";
};

export type KnowledgeGraphNodeListResponse = {
    items: KnowledgeGraphNode[];
    total: number;
    release_version: string;
    backend: "mysql" | "neo4j";
};

export type KnowledgeGraphSubgraphResponse = {
    nodes: KnowledgeGraphNode[];
    edges: KnowledgeGraphEdge[];
    paths: KnowledgeGraphPath[];
    release_version: string;
    backend: "mysql" | "neo4j";
    partial: boolean;
};

export type KnowledgeGraphOntologyType = {
    type_name: string;
    label: string;
    description: string;
    node_count: number;
    relation_count: number;
};

export type KnowledgeGraphOntologyRelation = {
    relation_type: string;
    label: string;
    description: string;
    source_types: string[];
    target_types: string[];
    edge_count: number;
};

export type KnowledgeGraphOntologyResponse = {
    release_version: string;
    scope: "business" | "schema" | "all";
    object_types: KnowledgeGraphOntologyType[];
    relation_types: KnowledgeGraphOntologyRelation[];
    backend: "mysql" | "neo4j";
};

export type KnowledgeGraphEvidence = {
    edge_id: string;
    period?: string | null;
    order_count?: number | null;
    sales_amount?: number | null;
    share?: number | null;
    rank?: number | null;
    confidence?: number | null;
    source_refs: Array<Record<string, unknown>>;
};

export type KnowledgeGraphGraphResponse = {
    view: KnowledgeGraphView;
    release_version: string;
    nodes: KnowledgeGraphNode[];
    edges: KnowledgeGraphEdge[];
    paths: KnowledgeGraphPath[];
    evidence: KnowledgeGraphEvidence[];
    partial: boolean;
    backend: "mysql" | "neo4j";
};

const NODE_TYPE_LABELS: Record<KnowledgeGraphNodeType, string> = {
    table: "数据表",
    column: "字段",
    cube: "Cube",
    semantic_member: "语义成员",
    metric_equivalence_group: "指标等效组",
    business_term: "业务术语",
    value: "业务取值",
    customer_segment: "客户群体",
    customer: "客户",
    product: "商品",
    category: "品类",
    brand: "品牌",
    region: "地区",
    metric: "业务指标",
    time_period: "时间周期",
};

export function knowledgeGraphNodeTypeLabel(type: KnowledgeGraphNodeType): string {
    return NODE_TYPE_LABELS[type];
}

export function knowledgeGraphReleaseLabel(release: KnowledgeGraphRelease): string {
    return release.active ? `${release.release_version} · 当前` : release.release_version;
}

export function knowledgeGraphErrorMessage(error: unknown): string {
    if (!(error instanceof Error) || !error.message) {
        return "知识图谱加载失败，请稍后重试";
    }
    const safeMessages = new Set([
        "登录已失效，请重新登录",
        "没有知识图谱管理权限",
        "知识图谱版本或节点不存在",
        "知识图谱服务暂不可用，请稍后重试",
        "知识图谱版本加载失败",
        "知识图谱节点加载失败",
        "知识图谱关系加载失败",
    ]);
    return safeMessages.has(error.message)
        ? error.message
        : "知识图谱加载失败，请稍后重试";
}
