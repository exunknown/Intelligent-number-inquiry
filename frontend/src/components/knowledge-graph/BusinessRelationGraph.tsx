import "@xyflow/react/dist/style.css";
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, applyNodeChanges, type Edge, type Node, type NodeProps, type NodeChange } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { knowledgeGraphNodeTypeLabel, knowledgeGraphRelationLabel, type KnowledgeGraphGraphResponse, type KnowledgeGraphNode } from "../../lib/knowledgeGraph";

type GraphNodeData = { node: KnowledgeGraphNode };
type GraphNode = Node<GraphNodeData>;

function BusinessNode({ data, selected }: NodeProps<GraphNode>) {
    const tone = data.node.node_type === "product" ? "border-indigo/40 bg-indigo/5" : data.node.node_type === "category" ? "border-amber/40 bg-amber/5" : data.node.node_type === "customer_segment" ? "border-cinnabar/40 bg-cinnabar/5" : "border-pine/30 bg-pine/5";
    return <div className={`relative min-w-[156px] border px-3 py-2.5 shadow-line ${tone} ${selected ? "ring-2 ring-cinnabar/35" : ""}`}><Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-cinnabar" /><div className="truncate text-sm font-semibold text-ink" title={data.node.title}>{data.node.title}</div><div className="mt-1 text-[10px] text-ink/50">{knowledgeGraphNodeTypeLabel(data.node.node_type)}</div><Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-cinnabar" /></div>;
}

const nodeTypes = { business: BusinessNode };

type BusinessRelationGraphProps = {
    graph: KnowledgeGraphGraphResponse | null;
    loading: boolean;
    selectedNodeId: string | null;
    selectedEdgeId: string | null;
    onSelectNode: (nodeId: string) => void;
    onSelectEdge: (edgeId: string) => void;
};

function layout(nodes: KnowledgeGraphNode[]): GraphNode[] {
    return nodes.map((node, index) => ({ id: node.node_id, type: "business", position: { x: 80 + (index % 4) * 245, y: 60 + Math.floor(index / 4) * 140 }, data: { node } }));
}

export function BusinessRelationGraph({ graph, loading, selectedNodeId, selectedEdgeId, onSelectNode, onSelectEdge }: BusinessRelationGraphProps) {
    const initialNodes = useMemo(() => layout(graph?.nodes ?? []), [graph]);
    const [nodes, setNodes] = useState<GraphNode[]>(initialNodes);
    useEffect(() => setNodes(initialNodes), [initialNodes]);
    const edges = useMemo<Edge[]>(() => {
        const nodeIds = new Set((graph?.nodes ?? []).map((node) => node.node_id));
        return (graph?.edges ?? []).filter((edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id)).map((edge) => ({ id: edge.edge_id, source: edge.source_node_id, target: edge.target_node_id, label: knowledgeGraphRelationLabel(edge.edge_type), markerEnd: { type: MarkerType.ArrowClosed, color: selectedEdgeId === edge.edge_id ? "#0E7490" : "#94A3B8" }, style: { stroke: selectedEdgeId === edge.edge_id ? "#0E7490" : "#94A3B8", strokeWidth: selectedEdgeId === edge.edge_id ? 2.4 : 1.2 }, labelStyle: { fill: "#64748B", fontSize: 10 }, labelBgStyle: { fill: "#FFFFFF", fillOpacity: 0.88 } }));
    }, [graph, selectedEdgeId]);
    if (loading) return <div className="grid min-h-[620px] place-items-center border border-ink/10 bg-white text-sm text-ink/45">正在展开业务关系…</div>;
    if (!graph || graph.nodes.length === 0) return <div className="grid min-h-[620px] place-items-center border border-ink/10 bg-white text-sm text-ink/45">当前版本暂无业务关系数据</div>;
    return <div className="relative min-h-[620px] overflow-hidden border border-ink/10 bg-white shadow-line"><div className="absolute left-4 top-4 z-10 border border-ink/10 bg-white/90 px-3 py-2 text-xs text-ink/55">{graph.nodes.length} 个对象 · {graph.edges.length} 条经营关系{graph.partial ? " · 已按预算截断" : ""}</div><ReactFlow nodes={nodes.map((node) => ({ ...node, selected: node.id === selectedNodeId }))} edges={edges} nodeTypes={nodeTypes} onNodesChange={(changes: NodeChange<GraphNode>[]) => setNodes((current) => applyNodeChanges(changes, current) as GraphNode[])} onNodeClick={(_, node) => onSelectNode(node.id)} onEdgeClick={(_, edge) => onSelectEdge(edge.id)} fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.35} maxZoom={1.6}><Background color="#D6E0E6" gap={24} size={1} /><Controls showInteractive={false} /><MiniMap pannable zoomable nodeColor="#0E7490" /></ReactFlow></div>;
}
