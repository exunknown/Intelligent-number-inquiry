export const KNOWLEDGE_GRAPH_NODE_TYPES = [
    "table",
    "column",
    "cube",
    "semantic_member",
    "metric_equivalence_group",
    "business_term",
    "value",
] as const;

export type KnowledgeGraphNodeType = (typeof KNOWLEDGE_GRAPH_NODE_TYPES)[number];

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

const NODE_TYPE_LABELS: Record<KnowledgeGraphNodeType, string> = {
    table: "数据表",
    column: "字段",
    cube: "Cube",
    semantic_member: "语义成员",
    metric_equivalence_group: "指标等效组",
    business_term: "业务术语",
    value: "业务取值",
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
