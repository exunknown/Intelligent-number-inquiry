import { Search } from "lucide-react";
import type { SemanticMemberSummary } from "../lib/semanticModel";

type MemberType = "all" | "measure" | "dimension" | "time_dimension";

type SemanticMemberListProps = {
    items: SemanticMemberSummary[];
    selectedId: string | null;
    filters: { memberType: MemberType; query: string };
    loading: boolean;
    error: string | null;
    onSelect: (memberId: string) => void;
    onFilterChange: (filters: { memberType: MemberType; query: string }) => void;
};

const typeLabels: Record<MemberType, string> = {
    all: "全部",
    measure: "指标",
    dimension: "维度",
    time_dimension: "时间",
};

const memberTypeLabel: Record<Exclude<MemberType, "all">, string> = {
    measure: "指标",
    dimension: "维度",
    time_dimension: "时间维度",
};

export function SemanticMemberList({
    items,
    selectedId,
    filters,
    loading,
    error,
    onSelect,
    onFilterChange,
}: SemanticMemberListProps) {
    return (
        <section className="flex min-h-0 w-[21rem] shrink-0 flex-col border-r border-ink/10 bg-white">
            <div className="border-b border-ink/10 p-4">
                <div className="mb-3 flex items-center justify-between">
                    <div>
                        <p className="font-serif text-lg font-bold text-ink">成员目录</p>
                        <p className="mt-1 text-xs text-ink/50">按治理口径维护指标与维度</p>
                    </div>
                    <span className="font-mono text-xs text-ink/45">{items.length}</span>
                </div>
                <label className="relative block">
                    <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-ink/35" aria-hidden="true" />
                    <input
                        value={filters.query}
                        onChange={(event) => onFilterChange({ ...filters, query: event.target.value })}
                        placeholder="搜索名称、别名或表"
                        className="h-10 w-full border border-ink/15 bg-paper pl-9 pr-3 text-sm text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15"
                    />
                </label>
                <div className="mt-3 grid grid-cols-4 border border-ink/10 bg-paper p-1">
                    {(Object.keys(typeLabels) as MemberType[]).map((type) => (
                        <button
                            key={type}
                            type="button"
                            onClick={() => onFilterChange({ ...filters, memberType: type })}
                            className={`min-h-8 px-2 text-xs transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40 ${
                                filters.memberType === type
                                    ? "bg-dai text-paper"
                                    : "text-ink/60 hover:bg-white hover:text-ink"
                            }`}
                        >
                            {typeLabels[type]}
                        </button>
                    ))}
                </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
                {loading && <p className="p-5 text-sm text-ink/50">正在加载成员目录...</p>}
                {error && <p className="m-4 border-l-2 border-oxide bg-oxide/5 p-3 text-sm text-oxide">{error}</p>}
                {!loading && !error && items.length === 0 && (
                    <p className="p-5 text-sm text-ink/50">没有匹配的治理成员。</p>
                )}
                {!loading && !error && items.map((item) => {
                    const active = selectedId === item.member_id;
                    return (
                        <button
                            key={item.member_id}
                            type="button"
                            onClick={() => onSelect(item.member_id)}
                            className={`block w-full border-b border-ink/8 px-4 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cinnabar/40 ${
                                active ? "border-l-2 border-l-cinnabar bg-cinnabar/5 pl-[14px]" : "hover:bg-paper"
                            }`}
                        >
                            <div className="flex items-center justify-between gap-3">
                                <span className="truncate text-sm font-semibold text-ink">{item.title || item.member_name}</span>
                                <span className="shrink-0 text-[11px] text-indigo">{memberTypeLabel[item.member_type]}</span>
                            </div>
                            <div className="mt-1 flex items-center gap-2 text-xs text-ink/45">
                                <span className="truncate font-mono">{item.member_name}</span>
                                <span>·</span>
                                <span className="truncate">{item.cube_name}</span>
                            </div>
                        </button>
                    );
                })}
            </div>
        </section>
    );
}
