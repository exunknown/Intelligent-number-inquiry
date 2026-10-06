import { ArrowLeft, Database, Network, RefreshCw, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
    getKnowledgeGraphSubgraph,
    listKnowledgeGraphReleases,
    searchKnowledgeGraphNodes,
} from "../lib/agentApi";
import {
    KNOWLEDGE_GRAPH_NODE_TYPES,
    knowledgeGraphErrorMessage,
    knowledgeGraphNodeTypeLabel,
    knowledgeGraphReleaseLabel,
    type KnowledgeGraphNode,
    type KnowledgeGraphNodeType,
    type KnowledgeGraphReleaseListResponse,
    type KnowledgeGraphSubgraphResponse,
} from "../lib/knowledgeGraph";
import type { SemanticBuildTab } from "../lib/semanticModel";
import { AgentManagementTabs } from "./AgentManagementTabs";

type KnowledgeGraphPageProps = {
    onBack: () => void;
    onTabChange: (tab: SemanticBuildTab) => void;
};

const EMPTY_GRAPH: KnowledgeGraphSubgraphResponse | null = null;

export function KnowledgeGraphPage({ onBack, onTabChange }: KnowledgeGraphPageProps) {
    const [releaseData, setReleaseData] = useState<KnowledgeGraphReleaseListResponse | null>(null);
    const [selectedRelease, setSelectedRelease] = useState("");
    const [query, setQuery] = useState("");
    const [nodeType, setNodeType] = useState<KnowledgeGraphNodeType | "">("");
    const [nodes, setNodes] = useState<KnowledgeGraphNode[]>([]);
    const [total, setTotal] = useState(0);
    const [selectedNode, setSelectedNode] = useState<KnowledgeGraphNode | null>(null);
    const [subgraph, setSubgraph] = useState<KnowledgeGraphSubgraphResponse | null>(EMPTY_GRAPH);
    const [loading, setLoading] = useState(true);
    const [searching, setSearching] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [graphLoading, setGraphLoading] = useState(false);
    const requestGeneration = useRef(0);
    const graphGeneration = useRef(0);

    const loadReleases = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await listKnowledgeGraphReleases();
            setReleaseData(response);
            setSelectedRelease((current) => current || response.active_release_version || response.items[0]?.release_version || "");
        } catch (loadError) {
            setError(knowledgeGraphErrorMessage(loadError));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        void loadReleases();
    }, []);

    useEffect(() => {
        if (!selectedRelease) return;
        const generation = ++requestGeneration.current;
        const timer = window.setTimeout(() => {
            setSearching(true);
            setError(null);
            void searchKnowledgeGraphNodes(
                selectedRelease,
                query,
                nodeType || undefined,
            )
                .then((response) => {
                    if (generation !== requestGeneration.current) return;
                    setNodes(response.items);
                    setTotal(response.total);
                    setSelectedNode((current) =>
                        current && response.items.some((node) => node.node_id === current.node_id)
                            ? current
                            : null,
                    );
                })
                .catch((searchError: unknown) => {
                    if (generation === requestGeneration.current) setError(knowledgeGraphErrorMessage(searchError));
                })
                .finally(() => {
                    if (generation === requestGeneration.current) setSearching(false);
                });
        }, 220);
        return () => window.clearTimeout(timer);
    }, [nodeType, query, selectedRelease]);

    useEffect(() => {
        if (!selectedNode || !selectedRelease) {
            setSubgraph(EMPTY_GRAPH);
            return;
        }
        const generation = ++graphGeneration.current;
        setGraphLoading(true);
        void getKnowledgeGraphSubgraph(selectedRelease, selectedNode.node_id)
            .then((response) => {
                if (generation === graphGeneration.current) setSubgraph(response);
            })
            .catch((graphError: unknown) => {
                if (generation === graphGeneration.current) setError(knowledgeGraphErrorMessage(graphError));
            })
            .finally(() => {
                if (generation === graphGeneration.current) setGraphLoading(false);
            });
    }, [selectedNode, selectedRelease]);

    const release = releaseData?.items.find((item) => item.release_version === selectedRelease);

    return (
        <section role="region" aria-label="知识图谱管理" className="min-h-0 flex-1 overflow-hidden bg-canvas">
            <div className="flex h-full min-h-0 flex-col bg-paper">
                <header className="flex shrink-0 items-center justify-between gap-3 border-b border-ink/10 px-5 py-4 lg:px-7">
                    <button
                        type="button"
                        onClick={onBack}
                        className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-ink/15 px-3 text-sm font-semibold text-ink transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                    >
                        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                        返回工作台
                    </button>
                    <div className="flex items-center gap-2 text-xs text-ink/55">
                        <Network className="h-4 w-4 text-indigo" aria-hidden="true" />
                        <span>知识图谱</span>
                    </div>
                    <button
                        type="button"
                        onClick={() => void loadReleases()}
                        disabled={loading}
                        title="刷新知识图谱"
                        aria-label="刷新知识图谱"
                        className="grid h-10 w-10 place-items-center rounded-full text-ink/60 transition hover:bg-ink/5 disabled:opacity-40"
                    >
                        <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" />
                    </button>
                </header>

                <AgentManagementTabs activeTab="knowledge-graph" onChange={onTabChange} />

                <div className="min-h-0 flex-1 overflow-y-auto bg-canvas p-4 lg:p-6">
                    <div className="mx-auto flex min-h-full max-w-[1600px] flex-col gap-4">
                        <div className="flex flex-wrap items-end gap-3 border-b border-ink/10 pb-4">
                            <label className="min-w-[260px] flex-1 text-xs font-semibold text-ink/65">
                                <span className="mb-1.5 block">图谱版本</span>
                                <select
                                    value={selectedRelease}
                                    onChange={(event) => {
                                        setSelectedRelease(event.target.value);
                                        setSelectedNode(null);
                                    }}
                                    disabled={loading || !releaseData}
                                    className="h-10 w-full rounded-lg border border-ink/15 bg-white px-3 text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:opacity-50"
                                >
                                    {releaseData?.items.map((item) => (
                                        <option key={item.release_version} value={item.release_version}>
                                            {knowledgeGraphReleaseLabel(item)}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            <div className="flex min-h-10 items-center gap-2 rounded-lg border border-ink/10 bg-white px-3 text-xs text-ink/60">
                                <Database className="h-4 w-4 text-indigo" aria-hidden="true" />
                                <span>{releaseData?.backend === "neo4j" ? "Neo4j" : "Meta MySQL"}</span>
                            </div>
                            <div className="flex min-h-10 items-center gap-3 rounded-lg border border-ink/10 bg-white px-3 text-xs text-ink/60">
                                <span><strong className="font-semibold text-ink">{release?.node_count ?? 0}</strong> 节点</span>
                                <span><strong className="font-semibold text-ink">{release?.edge_count ?? 0}</strong> 关系</span>
                            </div>
                        </div>

                        {error && <div role="alert" className="border border-oxide/25 bg-oxide/5 px-4 py-3 text-sm text-oxide">{error}</div>}

                        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[280px_minmax(0,1fr)_280px]">
                            <aside className="min-h-[360px] border border-ink/10 bg-white p-4 shadow-line">
                                <div className="flex items-center justify-between gap-3">
                                    <h2 className="font-serif text-base font-bold text-ink">节点目录</h2>
                                    <span className="text-xs text-ink/45">{total} 项</span>
                                </div>
                                <label className="relative mt-3 block">
                                    <span className="sr-only">搜索节点</span>
                                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35" aria-hidden="true" />
                                    <input
                                        type="search"
                                        value={query}
                                        onChange={(event) => setQuery(event.target.value)}
                                        placeholder="搜索节点名称或编号"
                                        className="h-10 w-full rounded-lg border border-ink/15 bg-paper pl-9 pr-3 text-sm outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15"
                                    />
                                </label>
                                <label className="mt-3 block text-xs font-semibold text-ink/60">
                                    <span className="sr-only">节点类型</span>
                                    <select
                                        value={nodeType}
                                        onChange={(event) => setNodeType(event.target.value as KnowledgeGraphNodeType | "")}
                                        className="h-9 w-full rounded-lg border border-ink/15 bg-white px-2 text-xs font-normal text-ink outline-none focus:border-indigo/60"
                                    >
                                        <option value="">全部类型</option>
                                        {KNOWLEDGE_GRAPH_NODE_TYPES.map((type) => (
                                            <option key={type} value={type}>{knowledgeGraphNodeTypeLabel(type)}</option>
                                        ))}
                                    </select>
                                </label>
                                <div className="mt-4 space-y-1.5">
                                    {searching && <p className="px-2 py-3 text-xs text-ink/50">正在读取节点…</p>}
                                    {!searching && nodes.length === 0 && <p className="px-2 py-3 text-xs text-ink/50">暂无匹配节点</p>}
                                    {nodes.map((node) => (
                                        <button
                                            key={node.node_id}
                                            type="button"
                                            onClick={() => setSelectedNode(node)}
                                            className={`w-full rounded-lg border px-3 py-2.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40 ${selectedNode?.node_id === node.node_id ? "border-indigo/40 bg-indigo/5" : "border-transparent hover:border-ink/10 hover:bg-paper"}`}
                                        >
                                            <div className="truncate text-sm font-semibold text-ink">{node.title}</div>
                                            <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-ink/45">
                                                <span>{knowledgeGraphNodeTypeLabel(node.node_type)}</span>
                                                <span className="truncate font-mono">{node.node_id}</span>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            </aside>

                            <main className="flex min-h-[360px] min-w-0 flex-col border border-ink/10 bg-white shadow-line">
                                <div className="flex items-center justify-between gap-3 border-b border-ink/10 px-4 py-3">
                                    <div>
                                        <h2 className="font-serif text-base font-bold text-ink">关系区域</h2>
                                        <p className="mt-1 text-xs text-ink/45">{selectedNode ? `已选择：${selectedNode.title}` : "选择节点后查看关联关系"}</p>
                                    </div>
                                    {graphLoading && <span className="text-xs text-indigo">正在展开…</span>}
                                </div>
                                <div className="grid min-h-0 flex-1 place-items-center bg-[radial-gradient(circle_at_center,rgba(37,109,133,0.08),transparent_55%)] p-6 text-center">
                                    {subgraph ? (
                                        <div className="max-w-sm">
                                            <Network className="mx-auto h-10 w-10 text-indigo/60" aria-hidden="true" />
                                            <p className="mt-3 font-serif text-lg font-bold text-ink">已加载关联关系</p>
                                            <p className="mt-2 text-sm leading-6 text-ink/55">{subgraph.nodes.length} 个节点 · {subgraph.edges.length} 条关系 · {subgraph.paths.length} 条路径</p>
                                            <p className="mt-3 text-xs text-ink/40">交互式关系画布将在下一阶段接入。</p>
                                        </div>
                                    ) : (
                                        <div className="max-w-sm">
                                            <Network className="mx-auto h-10 w-10 text-ink/20" aria-hidden="true" />
                                            <p className="mt-3 font-serif text-lg font-bold text-ink/70">等待选择节点</p>
                                            <p className="mt-2 text-sm leading-6 text-ink/45">从左侧节点目录选择一个表、字段或业务取值。</p>
                                        </div>
                                    )}
                                </div>
                            </main>

                            <aside className="min-h-[360px] border border-ink/10 bg-white p-4 shadow-line">
                                <h2 className="font-serif text-base font-bold text-ink">节点详情</h2>
                                {selectedNode ? (
                                    <div className="mt-4 space-y-4 text-sm">
                                        <div>
                                            <div className="text-xs text-ink/45">名称</div>
                                            <div className="mt-1 break-words font-semibold text-ink">{selectedNode.title}</div>
                                        </div>
                                        <div>
                                            <div className="text-xs text-ink/45">类型</div>
                                            <div className="mt-1 text-ink/75">{knowledgeGraphNodeTypeLabel(selectedNode.node_type)}</div>
                                        </div>
                                        <div>
                                            <div className="text-xs text-ink/45">节点编号</div>
                                            <div className="mt-1 break-all font-mono text-xs text-ink/70">{selectedNode.node_id}</div>
                                        </div>
                                        <div>
                                            <div className="text-xs text-ink/45">说明</div>
                                            <div className="mt-1 leading-6 text-ink/70">{selectedNode.description || "暂无说明"}</div>
                                        </div>
                                        <div className="border-t border-ink/10 pt-3 text-xs text-ink/50">
                                            来源：{selectedNode.source} · 置信度：{selectedNode.confidence.toFixed(2)}
                                        </div>
                                    </div>
                                ) : (
                                    <p className="mt-4 text-sm leading-6 text-ink/45">选择节点后查看字段、表和业务取值信息。</p>
                                )}
                            </aside>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
