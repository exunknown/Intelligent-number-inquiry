import { ArrowRight, Boxes, Link2 } from "lucide-react";
import { useMemo, useState } from "react";
import type { KnowledgeGraphOntologyResponse } from "../../lib/knowledgeGraph";

type OntologyWorkbenchProps = {
    ontology: KnowledgeGraphOntologyResponse | null;
    loading: boolean;
    search: string;
};

export function OntologyWorkbench({ ontology, loading, search }: OntologyWorkbenchProps) {
    const [selectedType, setSelectedType] = useState<string | null>(null);
    const types = useMemo(() => {
        const normalized = search.trim().toLowerCase();
        return (ontology?.object_types ?? []).filter((item) =>
            !normalized || `${item.label} ${item.type_name}`.toLowerCase().includes(normalized),
        );
    }, [ontology, search]);
    const relations = useMemo(() => {
        const normalized = search.trim().toLowerCase();
        return (ontology?.relation_types ?? []).filter((item) =>
            !normalized || `${item.label} ${item.relation_type}`.toLowerCase().includes(normalized),
        );
    }, [ontology, search]);
    const selected = types.find((item) => item.type_name === selectedType) ?? types[0];

    if (loading) {
        return <div className="grid min-h-[520px] place-items-center border border-ink/10 bg-white text-sm text-ink/45">正在读取本体定义…</div>;
    }

    return (
        <div className="grid min-h-[520px] gap-4 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
            <section className="border border-ink/10 bg-white p-4 shadow-line">
                <div className="flex items-center justify-between border-b border-ink/10 pb-3">
                    <h2 className="flex items-center gap-2 text-sm font-bold text-ink"><Boxes className="h-4 w-4 text-cinnabar" aria-hidden="true" />对象类型</h2>
                    <span className="font-mono text-[11px] text-ink/40">{types.length}</span>
                </div>
                <div className="mt-3 space-y-1.5">
                    {types.map((item) => (
                        <button
                            key={item.type_name}
                            type="button"
                            onClick={() => setSelectedType(item.type_name)}
                            className={`w-full border px-3 py-2 text-left transition ${selected?.type_name === item.type_name ? "border-cinnabar/30 bg-cinnabar/5" : "border-transparent hover:border-ink/10 hover:bg-paper"}`}
                        >
                            <div className="text-sm font-semibold text-ink">{item.label}</div>
                            <div className="mt-1 flex justify-between font-mono text-[10px] text-ink/40"><span>{item.type_name}</span><span>{item.node_count} 节点</span></div>
                        </button>
                    ))}
                </div>
            </section>
            <section className="border border-ink/10 bg-white p-5 shadow-line">
                {selected ? (
                    <>
                        <div className="flex items-start justify-between gap-4 border-b border-ink/10 pb-5">
                            <div><div className="text-xs font-semibold uppercase tracking-[0.16em] text-cinnabar">对象类型</div><h2 className="mt-2 font-serif text-2xl font-bold text-ink">{selected.label}</h2><p className="mt-2 max-w-xl text-sm leading-6 text-ink/55">{selected.description}</p></div>
                            <div className="rounded-md bg-paper px-3 py-2 text-right"><div className="font-mono text-lg font-bold text-ink">{selected.node_count}</div><div className="text-[11px] text-ink/45">当前版本节点</div></div>
                        </div>
                        <div className="mt-5 grid gap-3 sm:grid-cols-2">
                            <div className="border border-ink/10 bg-paper p-4"><div className="text-xs text-ink/45">稳定类型编码</div><div className="mt-2 font-mono text-sm text-ink">{selected.type_name}</div></div>
                            <div className="border border-ink/10 bg-paper p-4"><div className="text-xs text-ink/45">相关关系数</div><div className="mt-2 text-xl font-bold text-cinnabar">{selected.relation_count}</div></div>
                        </div>
                    </>
                ) : <div className="grid h-full min-h-[360px] place-items-center text-sm text-ink/45">选择一个对象类型查看治理定义</div>}
            </section>
            <section className="border border-ink/10 bg-white p-4 shadow-line">
                <div className="flex items-center justify-between border-b border-ink/10 pb-3"><h2 className="flex items-center gap-2 text-sm font-bold text-ink"><Link2 className="h-4 w-4 text-cinnabar" aria-hidden="true" />关系类型</h2><span className="font-mono text-[11px] text-ink/40">{relations.length}</span></div>
                <div className="mt-3 space-y-2">
                    {relations.map((item) => <div key={item.relation_type} className="border border-ink/10 bg-paper p-3"><div className="flex items-center gap-2 text-xs font-semibold text-ink"><span>{item.label}</span><ArrowRight className="h-3 w-3 text-cinnabar" aria-hidden="true" /><span className="font-mono text-[10px] text-ink/45">{item.edge_count}</span></div><div className="mt-2 font-mono text-[10px] leading-5 text-ink/45">{item.source_types.join(" / ")} → {item.target_types.join(" / ")}</div></div>)}
                </div>
            </section>
        </div>
    );
}
