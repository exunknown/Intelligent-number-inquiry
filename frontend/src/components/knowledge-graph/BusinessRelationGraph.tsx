import { Graph, type IEvent } from "@antv/g6";
import { useEffect, useRef } from "react";
import {
    knowledgeGraphRelationLabel,
    type KnowledgeGraphGraphResponse,
} from "../../lib/knowledgeGraph";

type BusinessRelationGraphProps = {
    graph: KnowledgeGraphGraphResponse | null;
    loading: boolean;
    selectedNodeId: string | null;
    selectedEdgeId: string | null;
    onSelectNode: (nodeId: string) => void;
    onSelectEdge: (edgeId: string) => void;
};

const nodeTones: Record<string, { fill: string; stroke: string; label: string }> = {
    brand: { fill: "#EDE9FE", stroke: "#7C3AED", label: "品牌" },
    product: { fill: "#DBEAFE", stroke: "#2563EB", label: "商品" },
    category: { fill: "#FEF3C7", stroke: "#D97706", label: "品类" },
    region: { fill: "#CCFBF1", stroke: "#0F766E", label: "区域" },
    customer: { fill: "#E0E7FF", stroke: "#4F46E5", label: "客户" },
    customer_segment: { fill: "#FCE7F3", stroke: "#DB2777", label: "客户群体" },
    metric: { fill: "#D1FAE5", stroke: "#059669", label: "经营指标" },
    time_period: { fill: "#ECFDF5", stroke: "#10B981", label: "时间周期" },
};

function toneForType(nodeType: string) {
    return nodeTones[nodeType] ?? {
        fill: "#D1FAE5",
        stroke: "#059669",
        label: "经营对象",
    };
}

function eventTargetId(event: IEvent) {
    if (!("target" in event)) return null;
    const target = event.target as { id?: string | number };
    return target.id === undefined ? null : String(target.id);
}

function toGraphData(graph: KnowledgeGraphGraphResponse) {
    const nodeIds = new Set(graph.nodes.map((node) => node.node_id));

    return {
        nodes: graph.nodes.map((node) => ({
            id: node.node_id,
            data: {
                title: node.title,
                nodeType: node.node_type,
            },
        })),
        edges: graph.edges
            .filter((edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id))
            .map((edge) => ({
                id: edge.edge_id,
                source: edge.source_node_id,
                target: edge.target_node_id,
                data: { label: knowledgeGraphRelationLabel(edge.edge_type) },
            })),
    };
}

function applySelection(
    instance: Graph,
    previousSelectionRef: { current: string[] },
    selectedNodeId: string | null,
    selectedEdgeId: string | null,
) {
    if (instance.destroyed) return;

    const currentSelection = [selectedNodeId, selectedEdgeId].filter(
        (id): id is string => Boolean(id),
    );
    const states: Record<string, "selected" | []> = {};
    for (const id of previousSelectionRef.current) {
        if (!currentSelection.includes(id)) states[id] = [];
    }
    for (const id of currentSelection) states[id] = "selected";
    previousSelectionRef.current = currentSelection;
    if (Object.keys(states).length > 0) {
        void instance.setElementState(states).catch(() => undefined);
    }
}

export function BusinessRelationGraph({
    graph,
    loading,
    selectedNodeId,
    selectedEdgeId,
    onSelectNode,
    onSelectEdge,
}: BusinessRelationGraphProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const graphRef = useRef<Graph | null>(null);
    const renderedGraphRef = useRef<Graph | null>(null);
    const previousSelectionRef = useRef<string[]>([]);
    const selectionRef = useRef({
        selectedNodeId,
        selectedEdgeId,
    });
    selectionRef.current = { selectedNodeId, selectedEdgeId };

    useEffect(() => {
        const container = containerRef.current;
        if (loading || !container || !graph || graph.nodes.length === 0) return;
        let disposed = false;
        let renderSettled = false;

        const instance = new Graph({
            container,
            autoFit: "view",
            padding: 56,
            data: toGraphData(graph),
            node: {
                type: "circle",
                style: {
                    size: 24,
                    fill: (datum) => toneForType(String(datum.data?.nodeType)).fill,
                    stroke: (datum) => toneForType(String(datum.data?.nodeType)).stroke,
                    lineWidth: 2,
                    labelText: (datum) => String(datum.data?.title ?? datum.id),
                    labelFill: "#1F2937",
                    labelFontSize: 11,
                    labelPlacement: "bottom",
                    labelOffsetY: 8,
                    labelMaxWidth: 150,
                },
                state: {
                    selected: {
                        lineWidth: 4,
                        stroke: "#C2410C",
                        halo: true,
                        haloStroke: "#C2410C",
                        haloLineWidth: 8,
                        haloStrokeOpacity: 0.18,
                    },
                },
            },
            edge: {
                type: "quadratic",
                style: {
                    stroke: "#94A3B8",
                    lineWidth: 1.2,
                    endArrow: true,
                    labelText: (datum) => String(datum.data?.label ?? ""),
                    labelFill: "#64748B",
                    labelFontSize: 10,
                    labelBackground: true,
                    labelBackgroundFill: "#FFFFFF",
                    labelBackgroundOpacity: 0.86,
                    labelPadding: [2, 4],
                },
                state: {
                    selected: {
                        stroke: "#0E7490",
                        lineWidth: 2.6,
                    },
                },
            },
            layout: {
                type: "d3-force",
                animation: false,
                link: { distance: 150 },
                manyBody: { strength: -180 },
                collide: { radius: 42 },
            },
            behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
        });

        graphRef.current = instance;
        renderedGraphRef.current = null;
        instance.on("node:click", (event) => {
            const nodeId = eventTargetId(event);
            if (nodeId) onSelectNode(nodeId);
        });
        instance.on("edge:click", (event) => {
            const edgeId = eventTargetId(event);
            if (edgeId) onSelectEdge(edgeId);
        });
        void instance.render()
            .then(() => {
                if (disposed || instance.destroyed) return;
                renderedGraphRef.current = instance;
                applySelection(
                    instance,
                    previousSelectionRef,
                    selectionRef.current.selectedNodeId,
                    selectionRef.current.selectedEdgeId,
                );
            })
            .catch(() => {
                if (graphRef.current === instance) {
                    graphRef.current = null;
                    renderedGraphRef.current = null;
                }
            })
            .finally(() => {
                renderSettled = true;
                if (disposed && !instance.destroyed) instance.destroy();
            });

        return () => {
            disposed = true;
            if (graphRef.current === instance) graphRef.current = null;
            if (renderedGraphRef.current === instance) {
                renderedGraphRef.current = null;
            }
            previousSelectionRef.current = [];
            if (renderSettled && !instance.destroyed) instance.destroy();
        };
    }, [graph, loading, onSelectEdge, onSelectNode]);

    useEffect(() => {
        const instance = renderedGraphRef.current;
        if (!instance) return;
        applySelection(
            instance,
            previousSelectionRef,
            selectedNodeId,
            selectedEdgeId,
        );
    }, [selectedEdgeId, selectedNodeId]);

    if (loading) return <div className="grid min-h-[620px] place-items-center border border-ink/10 bg-white text-sm text-ink/45">正在展开业务关系…</div>;
    if (!graph || graph.nodes.length === 0) return <div className="grid min-h-[620px] place-items-center border border-ink/10 bg-white text-sm text-ink/45">当前版本暂无业务关系数据</div>;

    const legendTypes = Array.from(new Set(graph.nodes.map((node) => node.node_type)))
        .sort((left, right) =>
            toneForType(left).label.localeCompare(toneForType(right).label),
        );

    return (
        <div className="relative min-h-[620px] overflow-hidden border border-ink/10 bg-white shadow-line" aria-label="业务关系图">
            <div className="pointer-events-none absolute left-4 top-4 z-10 border border-ink/10 bg-white/90 px-3 py-2 text-xs text-ink/55">
                {graph.nodes.length} 个对象 · {graph.edges.length} 条经营关系{graph.partial ? " · 已按预算截断" : ""}
            </div>
            <div className="pointer-events-none absolute bottom-4 left-4 z-10 flex flex-wrap gap-2 border border-ink/10 bg-white/90 px-3 py-2 text-[11px] text-ink/60">
                {legendTypes.map((type) => {
                    const tone = toneForType(type);
                    return (
                        <span key={type} className="flex items-center gap-1.5">
                            <i
                                className="h-2.5 w-2.5 rounded-full"
                                style={{
                                    backgroundColor: tone.fill,
                                    border: `2px solid ${tone.stroke}`,
                                }}
                            />
                            {tone.label}
                        </span>
                    );
                })}
            </div>
            <div ref={containerRef} className="h-[620px] w-full" />
        </div>
    );
}
