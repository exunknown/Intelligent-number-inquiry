import { ArrowLeft, Network, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    getKnowledgeGraphGraph,
    listKnowledgeGraphOntology,
    listKnowledgeGraphReleases,
} from "../lib/agentApi";
import {
    knowledgeGraphErrorMessage,
    type KnowledgeGraphGraphResponse,
    type KnowledgeGraphOntologyResponse,
    type KnowledgeGraphReleaseListResponse,
    type KnowledgeGraphScenario,
} from "../lib/knowledgeGraph";
import { BusinessRelationGraph } from "./knowledge-graph/BusinessRelationGraph";
import { GraphDetailPanel } from "./knowledge-graph/GraphDetailPanel";
import {
    KnowledgeGraphToolbar,
    type KnowledgeGraphWorkspace,
} from "./knowledge-graph/KnowledgeGraphToolbar";
import { OntologyWorkbench } from "./knowledge-graph/OntologyWorkbench";
import { SchemaGraph } from "./knowledge-graph/SchemaGraph";

type KnowledgeGraphPageProps = {
    onBack: () => void;
};

const objectTypeOptions = [
    ["product", "商品"],
    ["category", "品类"],
    ["brand", "品牌"],
    ["customer_segment", "客户群体"],
    ["region", "地区"],
] as const;

const relationTypeOptions = [
    ["SEGMENT_PREFERS_CATEGORY", "偏好"],
    ["PRODUCT_HOT_IN_REGION", "热销于"],
    ["PRODUCT_ASSOCIATED_WITH_PRODUCT", "关联购买"],
    ["METRIC_MEASURES_OBJECT", "指标度量"],
] as const;

function filterGraph(
    graph: KnowledgeGraphGraphResponse | null,
    search: string,
    objectTypes: string[],
    relationTypes: string[],
): KnowledgeGraphGraphResponse | null {
    if (!graph) return null;
    const needle = search.trim().toLowerCase();
    const nodes = graph.nodes.filter((node) =>
        (!objectTypes.length || objectTypes.includes(node.node_type)) &&
        `${node.title} ${node.node_id}`.toLowerCase().includes(needle),
    );
    const nodeIds = new Set(nodes.map((node) => node.node_id));
    const edges = graph.edges.filter((edge) =>
        (!relationTypes.length || relationTypes.includes(edge.edge_type)) &&
        nodeIds.has(edge.source_node_id) &&
        nodeIds.has(edge.target_node_id),
    );
    const edgeIds = new Set(edges.map((edge) => edge.edge_id));
    return { ...graph, nodes, edges, paths: graph.paths.filter((path) => path.node_ids.every((id) => nodeIds.has(id)) && path.edge_ids.every((id) => edgeIds.has(id))), evidence: graph.evidence.filter((item) => edgeIds.has(item.edge_id)) };
}

export function KnowledgeGraphPage({ onBack }: KnowledgeGraphPageProps) {
    const [releaseData, setReleaseData] = useState<KnowledgeGraphReleaseListResponse | null>(null);
    const [selectedRelease, setSelectedRelease] = useState("");
    const [workspace, setWorkspace] = useState<KnowledgeGraphWorkspace>("relation");
    const [scenario, setScenario] = useState<KnowledgeGraphScenario>("product");
    const [search, setSearch] = useState("");
    const [ontology, setOntology] = useState<KnowledgeGraphOntologyResponse | null>(null);
    const [graph, setGraph] = useState<KnowledgeGraphGraphResponse | null>(null);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
    const [objectTypes, setObjectTypes] = useState<string[]>([]);
    const [relationTypes, setRelationTypes] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);
    const [contentLoading, setContentLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const generation = useRef(0);

    const loadReleases = useCallback(async () => {
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
    }, []);

    useEffect(() => {
        void loadReleases();
    }, [loadReleases]);

    useEffect(() => {
        if (!selectedRelease) return;
        const currentGeneration = ++generation.current;
        setContentLoading(true);
        setError(null);
        const request = workspace === "ontology"
            ? listKnowledgeGraphOntology(selectedRelease, "all").then((response) => {
                if (currentGeneration !== generation.current) return;
                setOntology(response);
                setGraph(null);
            })
            : getKnowledgeGraphGraph({
                releaseVersion: selectedRelease,
                view: workspace,
                scenario: workspace === "relation" ? scenario : undefined,
                maxHops: 2,
                maxNodes: 80,
                maxEdges: 160,
                includeEvidence: true,
            }).then((response) => {
                if (currentGeneration !== generation.current) return;
                setGraph(response);
                setOntology(null);
            });
        void request.catch((loadError: unknown) => {
            if (currentGeneration === generation.current) setError(knowledgeGraphErrorMessage(loadError));
        }).finally(() => {
            if (currentGeneration === generation.current) setContentLoading(false);
        });
    }, [scenario, selectedRelease, workspace]);

    const visibleGraph = useMemo(
        () => filterGraph(graph, search, objectTypes, relationTypes),
        [graph, objectTypes, relationTypes, search],
    );
    const selectedNode = visibleGraph?.nodes.find((node) => node.node_id === selectedNodeId) ?? null;
    const selectedEdge = visibleGraph?.edges.find((edge) => edge.edge_id === selectedEdgeId) ?? null;
    const selectedEvidence = visibleGraph?.evidence.find((item) => item.edge_id === selectedEdgeId) ?? null;
    const release = releaseData?.items.find((item) => item.release_version === selectedRelease);

    return (
        <section role="region" aria-label="知识图谱工作台" className="min-h-0 flex-1 overflow-hidden bg-canvas">
            <div className="flex h-full min-h-0 flex-col bg-paper">
                <header className="flex shrink-0 items-center justify-between gap-4 border-b border-ink/10 px-5 py-4 lg:px-8">
                    <div className="flex min-w-0 items-center gap-3">
                        <button type="button" onClick={onBack} title="返回工作台" aria-label="返回工作台" className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink/60 transition hover:bg-ink/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"><ArrowLeft className="h-4 w-4" aria-hidden="true" /></button>
                        <div className="flex min-w-0 items-center gap-2"><Network className="h-5 w-5 shrink-0 text-pine" aria-hidden="true" /><div><h1 className="truncate font-serif text-xl font-bold text-ink">业务知识图谱</h1><p className="text-xs text-ink/45">商品经营 · 客户行为 · 区域经营</p></div></div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2"><span className="hidden border border-ink/15 bg-white px-3 py-2 text-xs text-ink/65 sm:inline">{selectedRelease || "暂无版本"}</span>{release?.active && <span className="bg-pine px-3 py-2 text-xs font-semibold text-white">当前版本</span>}<button type="button" onClick={() => void loadReleases()} disabled={loading} title="刷新知识图谱" aria-label="刷新知识图谱" className="grid h-10 w-10 place-items-center rounded-full text-ink/60 transition hover:bg-ink/5 disabled:opacity-40"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" /></button></div>
                </header>
                <KnowledgeGraphToolbar releases={releaseData?.items ?? []} selectedRelease={selectedRelease} backend={releaseData?.backend ?? "mysql"} workspace={workspace} scenario={scenario} search={search} onReleaseChange={(value) => { setSelectedRelease(value); setSelectedNodeId(null); setSelectedEdgeId(null); }} onWorkspaceChange={(value) => { setWorkspace(value); setSelectedNodeId(null); setSelectedEdgeId(null); }} onScenarioChange={(value) => { setScenario(value); setWorkspace("relation"); setSelectedNodeId(null); setSelectedEdgeId(null); }} onSearchChange={setSearch} />
                <div className="min-h-0 flex-1 overflow-y-auto bg-canvas p-4 lg:p-6">
                    <div className="mx-auto grid min-h-full max-w-[1800px] gap-4 xl:grid-cols-[220px_minmax(0,1fr)_300px]">
                        <aside className="border border-ink/10 bg-white p-4 shadow-line" aria-label="图谱筛选">
                            <div className="flex items-center justify-between border-b border-ink/10 pb-3"><h2 className="text-sm font-bold text-ink">经营对象</h2><button type="button" onClick={() => setObjectTypes([])} className="text-[11px] text-ink/45 hover:text-cinnabar">清空</button></div>
                            <div className="mt-3 space-y-1">{objectTypeOptions.map(([type, label]) => { const checked = !objectTypes.length || objectTypes.includes(type); return <button key={type} type="button" aria-pressed={checked} onClick={() => setObjectTypes((current) => checked && current.length === 0 ? objectTypeOptions.filter(([value]) => value !== type).map(([value]) => value) : checked ? current.filter((value) => value !== type) : [...current, type])} className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm transition ${checked ? "bg-pine/10 font-semibold text-pine" : "text-ink/55 hover:bg-paper"}`}><span>{label}</span><span className="text-[10px] text-ink/35">{visibleGraph?.nodes.filter((node) => node.node_type === type).length ?? 0}</span></button>; })}</div>
                            <div className="mt-6 border-b border-ink/10 pb-3"><h2 className="text-sm font-bold text-ink">关系筛选</h2></div>
                            <div className="mt-3 space-y-2">{relationTypeOptions.map(([type, label]) => { const checked = !relationTypes.length || relationTypes.includes(type); return <label key={type} className="flex items-center gap-2 px-1 py-1 text-xs text-ink/65"><input type="checkbox" checked={checked} onChange={() => setRelationTypes((current) => checked && current.length === 0 ? relationTypeOptions.filter(([value]) => value !== type).map(([value]) => value) : checked ? current.filter((value) => value !== type) : [...current, type])} className="accent-pine" />{label}</label>; })}</div>
                        </aside>
                        <main className="min-w-0">
                            <div className="mb-3 flex items-center justify-between gap-3 border-b border-ink/10 pb-3 text-xs text-ink/50"><span>{release ? `${release.node_count} 个对象 · ${release.edge_count} 条关系` : "等待图谱版本"}</span>{contentLoading && <span className="text-cinnabar">正在读取图谱…</span>}</div>
                            {error && <div role="alert" className="mb-3 border border-oxide/25 bg-oxide/5 px-4 py-3 text-sm text-oxide">{error}</div>}
                            {workspace === "ontology" ? <OntologyWorkbench ontology={ontology} loading={contentLoading} search={search} /> : workspace === "relation" ? <BusinessRelationGraph graph={visibleGraph} loading={contentLoading} selectedNodeId={selectedNodeId} selectedEdgeId={selectedEdgeId} onSelectNode={setSelectedNodeId} onSelectEdge={setSelectedEdgeId} /> : <SchemaGraph graph={visibleGraph} loading={contentLoading} selectedNodeId={selectedNodeId} selectedEdgeId={selectedEdgeId} onSelectNode={setSelectedNodeId} onSelectEdge={setSelectedEdgeId} />}
                        </main>
                        <GraphDetailPanel view={workspace === "ontology" ? "schema" : workspace} node={selectedNode} edge={selectedEdge} evidence={selectedEvidence} />
                    </div>
                </div>
            </div>
        </section>
    );
}
