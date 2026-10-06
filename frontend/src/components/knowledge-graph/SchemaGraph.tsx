import "@xyflow/react/dist/style.css";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, applyNodeChanges, type Edge, type Node, type NodeProps, type NodeChange } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { knowledgeGraphNodeTypeLabel, knowledgeGraphRelationLabel, type KnowledgeGraphGraphResponse, type KnowledgeGraphNode } from "../../lib/knowledgeGraph";

type SchemaNodeData = { node: KnowledgeGraphNode };
type SchemaNode = Node<SchemaNodeData>;

function SchemaNodeCard({ data, selected }: NodeProps<SchemaNode>) {
    const role = typeof data.node.metadata.role === "string" ? data.node.metadata.role : "schema";
    return <div className={`relative min-w-[190px] border-t-4 border-indigo bg-white px-4 py-3 shadow-line ${selected ? "ring-2 ring-cinnabar/35" : "border-x border-b border-ink/10"}`}><Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-indigo" /><div className="flex items-center gap-2 text-sm font-semibold text-ink"><span className="grid h-5 w-5 place-items-center bg-indigo/10 font-mono text-[10px] text-indigo">{data.node.node_type === "table" ? "T" : "F"}</span><span className="truncate" title={data.node.title}>{data.node.title}</span></div><div className="mt-2 font-mono text-[10px] text-ink/45">{knowledgeGraphNodeTypeLabel(data.node.node_type)} · {role}</div><Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-indigo" /></div>;
}

const nodeTypes = { schema: SchemaNodeCard };

type SchemaGraphProps = {
    graph: KnowledgeGraphGraphResponse | null;
    loading: boolean;
    selectedNodeId: string | null;
    selectedEdgeId: string | null;
    onSelectNode: (nodeId: string) => void;
    onSelectEdge: (edgeId: string) => void;
};

function layout(nodes: KnowledgeGraphNode[]): SchemaNode[] {
    return nodes.map((node, index) => ({ id: node.node_id, type: "schema", position: { x: 80 + (index % 3) * 310, y: 70 + Math.floor(index / 3) * 150 }, data: { node } }));
}

export function SchemaGraph({ graph, loading, selectedNodeId, selectedEdgeId, onSelectNode, onSelectEdge }: SchemaGraphProps) {
    const initialNodes = useMemo(() => layout(graph?.nodes ?? []), [graph]);
    const [nodes, setNodes] = useState<SchemaNode[]>(initialNodes);
    useEffect(() => setNodes(initialNodes), [initialNodes]);
    const edges = useMemo<Edge[]>(() => {
        const nodeIds = new Set((graph?.nodes ?? []).map((node) => node.node_id));
        return (graph?.edges ?? []).filter((edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id)).map((edge) => ({ id: edge.edge_id, source: edge.source_node_id, target: edge.target_node_id, label: knowledgeGraphRelationLabel(edge.edge_type), markerEnd: { type: MarkerType.ArrowClosed, color: selectedEdgeId === edge.edge_id ? "#256D85" : "#B0BEC8" }, style: { stroke: selectedEdgeId === edge.edge_id ? "#256D85" : "#B0BEC8", strokeWidth: selectedEdgeId === edge.edge_id ? 2.4 : 1.2 }, labelStyle: { fill: "#64748B", fontSize: 10 }, labelBgStyle: { fill: "#FFFFFF", fillOpacity: 0.9 } }));
    }, [graph, selectedEdgeId]);
    if (loading) return <div className="grid min-h-[620px] place-items-center border border-ink/10 bg-white text-sm text-ink/45">正在读取 Schema 图谱和字段…</div>;
    if (!graph || graph.nodes.length === 0) return <div className="grid min-h-[620px] place-items-center border border-ink/10 bg-white text-sm text-ink/45">当前版本暂无 Schema 关系数据</div>;
    return <div className="relative min-h-[620px] overflow-hidden border border-ink/10 bg-white shadow-line"><div className="absolute left-4 top-4 z-10 border border-ink/10 bg-white/90 px-3 py-2 text-xs text-ink/55">Schema 结构 · {graph.nodes.length} 个对象 · {graph.edges.length} 条关系</div><ReactFlow nodes={nodes.map((node) => ({ ...node, selected: node.id === selectedNodeId }))} edges={edges} nodeTypes={nodeTypes} onNodesChange={(changes: NodeChange<SchemaNode>[]) => setNodes((current) => applyNodeChanges(changes, current) as SchemaNode[])} onNodeClick={(_, node) => onSelectNode(node.id)} onEdgeClick={(_, edge) => onSelectEdge(edge.id)} fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.35} maxZoom={1.6}><Background color="#D6E0E6" gap={24} size={1} /><Controls showInteractive={false} /></ReactFlow></div>;
}
