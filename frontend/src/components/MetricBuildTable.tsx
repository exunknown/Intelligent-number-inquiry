import { Copy, Edit3 } from "lucide-react";
import type { SemanticMember } from "../lib/semanticModel";

export type MetricBuildTableProps = {
    items: SemanticMember[];
    loading: boolean;
    error: string | null;
    disabled: boolean;
    onEdit: (memberId: string, trigger: HTMLButtonElement) => void;
    onCopy: (memberId: string, trigger: HTMLButtonElement) => void;
};

export function MetricBuildTable({ items, loading, error, disabled, onEdit, onCopy }: MetricBuildTableProps) {
    const metrics = items.filter((member) => member.member_type === "measure");
    return <div id="agent-panel-metrics" role="tabpanel" aria-labelledby="agent-tab-metrics" className="min-h-0 overflow-auto border-y border-ink/10 bg-white">
        <table className="min-w-[980px] w-full text-left text-sm"><thead className="sticky top-0 z-10 bg-paper text-xs text-ink/55"><tr>{["指标名称", "指标编码", "Cube", "口径摘要", "关系数量", "状态", "更新时间", "操作"].map((heading) => <th key={heading} className="whitespace-nowrap px-5 py-3 font-semibold">{heading}</th>)}</tr></thead><tbody>
            {loading ? <tr><td colSpan={8} className="px-5 py-12 text-center text-sm text-ink/50">正在加载指标建设数据...</td></tr> : error ? <tr><td colSpan={8} role="alert" className="px-5 py-12 text-center text-sm text-oxide">{error}</td></tr> : metrics.length === 0 ? <tr><td colSpan={8} className="px-5 py-12 text-center text-sm text-ink/50">暂无指标，请从工具栏新增指标。</td></tr> : metrics.map((member) => <tr key={member.member_id} className="border-t border-ink/8 hover:bg-paper/60"><td className="px-5 py-4 font-semibold text-ink">{member.title || member.member_name}</td><td className="px-5 py-4 font-mono text-xs text-ink/65">{member.member_name}</td><td className="px-5 py-4 text-ink/70">{member.cube_name}</td><td className="max-w-xs px-5 py-4 text-ink/60">{member.calculation_note || "暂无口径说明"}</td><td className="px-5 py-4 text-ink/60">未提供</td><td className="px-5 py-4 text-ink/70">{member.status}</td><td className="px-5 py-4 text-ink/45">--</td><td className="px-5 py-4"><div className="flex gap-1"><button type="button" onClick={(event) => onEdit(member.member_id, event.currentTarget)} disabled={disabled} title="编辑指标" aria-label={`编辑指标 ${member.title || member.member_name}`} className="grid h-8 w-8 place-items-center rounded-full text-ink/55 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"><Edit3 className="h-4 w-4" aria-hidden="true" /></button><button type="button" onClick={(event) => onCopy(member.member_id, event.currentTarget)} disabled={disabled} title="复制指标" aria-label={`复制指标 ${member.title || member.member_name}`} className="grid h-8 w-8 place-items-center rounded-full text-ink/55 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"><Copy className="h-4 w-4" aria-hidden="true" /></button></div></td></tr>)}
        </tbody></table>
    </div>;
}
