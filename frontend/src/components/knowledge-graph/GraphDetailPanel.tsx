import { CircleAlert, FileText, Link2, Sparkles } from "lucide-react";
import {
    knowledgeGraphNodeTypeLabel,
    knowledgeGraphRelationLabel,
    type KnowledgeGraphEdge,
    type KnowledgeGraphEvidence,
    type KnowledgeGraphNode,
    type KnowledgeGraphView,
} from "../../lib/knowledgeGraph";

type GraphDetailPanelProps = {
    view: KnowledgeGraphView;
    node: KnowledgeGraphNode | null;
    edge: KnowledgeGraphEdge | null;
    evidence: KnowledgeGraphEvidence | null;
};

function formatValue(value: unknown) {
    if (typeof value === "number") return value.toLocaleString("zh-CN");
    return String(value);
}

export function GraphDetailPanel({ view, node, edge, evidence }: GraphDetailPanelProps) {
    return (
        <aside className="min-h-[620px] border border-ink/10 bg-white p-5 shadow-line" aria-label="当前对象详情">
            <div className="flex items-center gap-2 border-b border-ink/10 pb-4">
                <FileText className="h-4 w-4 text-pine" aria-hidden="true" />
                <h2 className="text-sm font-bold text-ink">当前对象</h2>
            </div>
            {node ? (
                <div className="mt-5 space-y-5">
                    <section>
                        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-pine">经营对象</div>
                        <h3 className="mt-2 break-words font-serif text-xl font-bold text-ink">{node.title}</h3>
                        <p className="mt-2 text-xs leading-5 text-ink/55">{node.description || "暂无说明"}</p>
                    </section>
                    <section className="border-t border-ink/10 pt-4">
                        <h4 className="text-xs font-bold text-ink">经营概览</h4>
                        <div className="mt-3 grid grid-cols-2 gap-2">
                            <div className="bg-paper p-3"><div className="text-[11px] text-ink/45">对象类型</div><div className="mt-1 text-sm font-semibold text-ink">{knowledgeGraphNodeTypeLabel(node.node_type)}</div></div>
                            <div className="bg-paper p-3"><div className="text-[11px] text-ink/45">置信度</div><div className="mt-1 text-sm font-semibold text-pine">{node.confidence.toFixed(2)}</div></div>
                        </div>
                        {Object.keys(node.metadata).length > 0 && <dl className="mt-3 space-y-2">{Object.entries(node.metadata).slice(0, 4).map(([key, value]) => <div key={key} className="flex justify-between gap-3 text-xs"><dt className="text-ink/45">{key}</dt><dd className="max-w-[150px] truncate text-right font-mono text-ink/70" title={String(value)}>{formatValue(value)}</dd></div>)}</dl>}
                    </section>
                    <section className="border-t border-ink/10 pt-4">
                        <h4 className="text-xs font-bold text-ink">关联洞察</h4>
                        {edge ? <div className="mt-3 bg-pine/5 p-3"><div className="flex items-center gap-2 text-xs font-semibold text-ink"><Link2 className="h-3.5 w-3.5 text-pine" aria-hidden="true" />{knowledgeGraphRelationLabel(edge.edge_type)}</div><p className="mt-2 break-words text-[11px] leading-5 text-ink/55">{edge.source_node_id} → {edge.target_node_id}</p></div> : <p className="mt-3 text-xs leading-5 text-ink/45">选择一条关系查看业务洞察。</p>}
                    </section>
                    <section className="border-t border-ink/10 pt-4">
                        <h4 className="flex items-center gap-2 text-xs font-bold text-ink"><Sparkles className="h-3.5 w-3.5 text-amber" aria-hidden="true" />数据证据</h4>
                        {evidence ? <div className="mt-3 grid grid-cols-2 gap-2">{evidence.order_count !== null && evidence.order_count !== undefined && <div className="bg-paper p-3"><div className="text-[11px] text-ink/45">订单数</div><div className="mt-1 text-sm font-bold text-cinnabar">{evidence.order_count}</div></div>}{evidence.sales_amount !== null && evidence.sales_amount !== undefined && <div className="bg-paper p-3"><div className="text-[11px] text-ink/45">销售额</div><div className="mt-1 text-sm font-bold text-cinnabar">¥{evidence.sales_amount.toLocaleString("zh-CN")}</div></div>}<div className="col-span-2 text-[11px] text-ink/45">证据来源 {evidence.source_refs.length} 条 · {view === "relation" ? "业务聚合" : "Schema 关系"}</div></div> : <p className="mt-3 text-xs leading-5 text-ink/45">选择关系后显示订单数、销售额和证据来源。</p>}
                    </section>
                </div>
            ) : (
                <div className="grid min-h-[520px] place-items-center text-center text-sm leading-6 text-ink/45"><div><CircleAlert className="mx-auto h-8 w-8 text-ink/20" aria-hidden="true" /><p className="mt-3">选择节点查看经营结论和关系证据</p></div></div>
            )}
        </aside>
    );
}
