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
import type { SemanticBuildTab } from "../lib/semanticModel";
import { AgentManagementTabs } from "./AgentManagementTabs";
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
    onTabChange: (tab: SemanticBuildTab) => void;
};

function filterGraph(graph: KnowledgeGraphGraphResponse | null, search: string): KnowledgeGraphGraphResponse | null {
    if (!graph || !search.trim()) return graph;
    const needle = search.trim().toLowerCase();
    const nodes = graph.nodes.filter((node) => `${node.title} ${node.node_id}`.toLowerCase().includes(needle));
    const nodeIds = new Set(nodes.map((node) => node.node_id));
    const edges = graph.edges.filter((edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id));
    const edgeIds = new Set(edges.map((edge) => edge.edge_id));
    return { ...graph, nodes, edges, paths: graph.paths.filter((path) => path.node_ids.every((id) => nodeIds.has(id)) && path.edge_ids.every((id) => edgeIds.has(id))), evidence: graph.evidence.filter((item) => edgeIds.has(item.edge_id)) };
}

export function KnowledgeGraphPage({ onBack, onTabChange }: KnowledgeGraphPageProps) {
    const [releaseData, setReleaseData] = useState<KnowledgeGraphReleaseListResponse | null>(null);
    const [selectedRelease, setSelectedRelease] = useState("");
    const [workspace, setWorkspace] = useState<KnowledgeGraphWorkspace>("ontology");
    const [scenario, setScenario] = useState<KnowledgeGraphScenario>("product");
    const [search, setSearch] = useState("");
    const [ontology, setOntology] = useState<KnowledgeGraphOntologyResponse | null>(null);
    const [graph, setGraph] = useState<KnowledgeGraphGraphResponse | null>(null);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
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

    const visibleGraph = useMemo(() => filterGraph(graph, search), [graph, search]);
    const selectedNode = visibleGraph?.nodes.find((node) => node.node_id === selectedNodeId) ?? null;
    const selectedEdge = visibleGraph?.edges.find((edge) => edge.edge_id === selectedEdgeId) ?? null;
    const selectedEvidence = visibleGraph?.evidence.find((item) => item.edge_id === selectedEdgeId) ?? null;
    const release = releaseData?.items.find((item) => item.release_version === selectedRelease);

    return (
        <section role="region" aria-label="知识图谱管理" className="min-h-0 flex-1 overflow-hidden bg-canvas">
            <div className="flex h-full min-h-0 flex-col bg-paper">
                <header className="flex shrink-0 items-center justify-between gap-3 border-b border-ink/10 px-5 py-4 lg:px-7">
                    <button type="button" onClick={onBack} className="inline-flex min-h-10 items-center gap-2 rounded-md border border-ink/15 px-3 text-sm font-semibold text-ink transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"><ArrowLeft className="h-4 w-4" aria-hidden="true" />返回工作台</button>
                    <div className="flex items-center gap-2 text-xs text-ink/55"><Network className="h-4 w-4 text-cinnabar" aria-hidden="true" /><span>知识图谱</span></div>
                    <button type="button" onClick={() => void loadReleases()} disabled={loading} title="刷新知识图谱" aria-label="刷新知识图谱" className="grid h-10 w-10 place-items-center rounded-full text-ink/60 transition hover:bg-ink/5 disabled:opacity-40"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" /></button>
                </header>
                <AgentManagementTabs activeTab="knowledge-graph" onChange={onTabChange} />
                <div className="min-h-0 flex-1 overflow-y-auto bg-canvas p-4 lg:p-6">
                    <div className="mx-auto flex min-h-full max-w-[1700px] flex-col gap-4">
                        <KnowledgeGraphToolbar releases={releaseData?.items ?? []} selectedRelease={selectedRelease} backend={releaseData?.backend ?? "mysql"} workspace={workspace} scenario={scenario} search={search} onReleaseChange={(value) => { setSelectedRelease(value); setSelectedNodeId(null); setSelectedEdgeId(null); }} onWorkspaceChange={(value) => { setWorkspace(value); setSelectedNodeId(null); setSelectedEdgeId(null); }} onScenarioChange={(value) => { setScenario(value); setWorkspace("relation"); setSelectedNodeId(null); setSelectedEdgeId(null); }} onSearchChange={setSearch} />
                        <span className="sr-only">本体底座 关系图 Schema 图谱 节点详情</span>
                        <div className="flex items-center justify-between gap-3 border-b border-ink/10 pb-3 text-xs text-ink/50"><span className="sr-only">节点目录</span><span>{release ? `${release.node_count} 个节点 · ${release.edge_count} 条关系` : "等待图谱版本"}</span>{contentLoading && <span className="text-cinnabar">正在读取图谱…</span>}</div>
                        {error && <div role="alert" className="border border-oxide/25 bg-oxide/5 px-4 py-3 text-sm text-oxide">{error}</div>}
                        {workspace === "ontology" ? <OntologyWorkbench ontology={ontology} loading={contentLoading} search={search} /> : <div className="grid min-h-0 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">{workspace === "relation" ? <BusinessRelationGraph graph={visibleGraph} loading={contentLoading} selectedNodeId={selectedNodeId} selectedEdgeId={selectedEdgeId} onSelectNode={setSelectedNodeId} onSelectEdge={setSelectedEdgeId} /> : <SchemaGraph graph={visibleGraph} loading={contentLoading} selectedNodeId={selectedNodeId} selectedEdgeId={selectedEdgeId} onSelectNode={setSelectedNodeId} onSelectEdge={setSelectedEdgeId} />}<GraphDetailPanel view={workspace} node={selectedNode} edge={selectedEdge} evidence={selectedEvidence} /></div>}
                    </div>
                </div>
            </div>
        </section>
    );
}
