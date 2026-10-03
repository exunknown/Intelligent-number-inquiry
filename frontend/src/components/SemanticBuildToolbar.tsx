import { Plus, RefreshCw, Search } from "lucide-react";
import type { SemanticBuildTab, SemanticMemberType } from "../lib/semanticModel";

export type SemanticBuildToolbarProps = {
    tab: SemanticBuildTab;
    query: string;
    memberType: "all" | SemanticMemberType;
    count: number;
    selectedCount: number;
    disabled: boolean;
    onQueryChange: (query: string) => void;
    onMemberTypeChange: (type: "all" | SemanticMemberType) => void;
    onRefresh: () => void;
    onCreate: (type: SemanticMemberType, trigger: HTMLButtonElement) => void;
};

export function SemanticBuildToolbar({ tab, query, memberType, count, selectedCount, disabled, onQueryChange, onMemberTypeChange, onRefresh, onCreate }: SemanticBuildToolbarProps) {
    const dimensionTab = tab === "dimensions";
    return (
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-ink/10 bg-paper px-5 py-4 lg:px-7">
            <span className="shrink-0 text-sm font-medium text-ink">已选（{selectedCount}）</span>
            <span className="h-5 w-px bg-ink/15" aria-hidden="true" />
            <label className="relative min-w-[280px] flex-1 lg:max-w-xl">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/40" aria-hidden="true" />
                <span className="sr-only">搜索成员</span>
                <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索名称、编码或 Cube" disabled={disabled} className="h-10 w-full rounded-xl border border-ink/15 bg-white pl-10 pr-3 text-sm text-ink outline-none transition placeholder:text-ink/35 focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-50" />
            </label>
            <div className="flex items-center gap-1 rounded-xl border border-ink/10 bg-white p-1" aria-label={dimensionTab ? "维度类型筛选" : "指标类型筛选"}>
                <button type="button" onClick={() => onMemberTypeChange("all")} disabled={disabled} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-45 ${memberType === "all" ? "bg-dai text-paper" : "text-ink/55 hover:bg-paper"}`}>{dimensionTab ? "全部维度" : "全部指标"}</button>
                {dimensionTab && <>
                    <button type="button" onClick={() => onMemberTypeChange("dimension")} disabled={disabled} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-45 ${memberType === "dimension" ? "bg-dai text-paper" : "text-ink/55 hover:bg-paper"}`}>普通维度</button>
                    <button type="button" onClick={() => onMemberTypeChange("time_dimension")} disabled={disabled} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-45 ${memberType === "time_dimension" ? "bg-dai text-paper" : "text-ink/55 hover:bg-paper"}`}>时间维度</button>
                </>}
            </div>
            <span className="text-xs text-ink/50">共 {count} 项</span>
            <button type="button" onClick={onRefresh} disabled={disabled} title="刷新建设数据" aria-label="刷新建设数据" className="grid h-10 w-10 place-items-center rounded-full text-ink/60 transition hover:bg-white hover:text-ink disabled:cursor-not-allowed disabled:opacity-45"><RefreshCw className="h-4 w-4" aria-hidden="true" /></button>
            {dimensionTab ? <div className="flex gap-2"><button type="button" onClick={(event) => onCreate("dimension", event.currentTarget)} disabled={disabled} className="inline-flex h-10 items-center gap-1.5 rounded-xl bg-dai px-3 text-sm font-semibold text-paper transition hover:bg-dai/90 disabled:cursor-not-allowed disabled:opacity-45"><Plus className="h-4 w-4" aria-hidden="true" />新增维度</button><button type="button" onClick={(event) => onCreate("time_dimension", event.currentTarget)} disabled={disabled} className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-dai bg-white px-3 text-sm font-semibold text-dai transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-45"><Plus className="h-4 w-4" aria-hidden="true" />新增时间维度</button></div> : <button type="button" onClick={(event) => onCreate("measure", event.currentTarget)} disabled={disabled} className="inline-flex h-10 items-center gap-1.5 rounded-xl bg-dai px-3 text-sm font-semibold text-paper transition hover:bg-dai/90 disabled:cursor-not-allowed disabled:opacity-45"><Plus className="h-4 w-4" aria-hidden="true" />新增指标</button>}
        </div>
    );
}
