import { useEffect, useState } from "react";
import type { SemanticMember } from "../lib/semanticModel";

export type MetricBuildTableProps = {
    items: SemanticMember[];
    loading: boolean;
    error: string | null;
    disabled: boolean;
    selectedIds: string[];
    onSelectionChange: (memberId: string, selected: boolean) => void;
    onEdit: (memberId: string, trigger: HTMLButtonElement) => void;
    onDelete: (memberId: string, trigger: HTMLButtonElement) => void;
};

const emptyValue = (value: string | null | undefined) => value || "–";
const PAGE_SIZE = 10;

export function MetricBuildTable({
    items,
    loading,
    error,
    disabled,
    selectedIds,
    onSelectionChange,
    onEdit,
    onDelete,
}: MetricBuildTableProps) {
    const metrics = items.filter((member) => member.member_type === "measure");
    const [page, setPage] = useState(1);
    const pageCount = Math.max(1, Math.ceil(metrics.length / PAGE_SIZE));
    const itemKey = metrics.map((member) => member.member_id).join("|");
    const pageItems = metrics.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    const allSelected = pageItems.length > 0 && pageItems.every((member) => selectedIds.includes(member.member_id));

    useEffect(() => {
        setPage(1);
    }, [itemKey]);

    const toggleAll = () => {
        pageItems.forEach((member) => onSelectionChange(member.member_id, !allSelected));
    };

    return (
        <div id="agent-panel-metrics" role="tabpanel" aria-labelledby="agent-tab-metrics" className="mx-8 my-5 min-h-0 max-h-[460px] overflow-auto overscroll-contain rounded-2xl border border-ink/15 bg-white shadow-line lg:mx-12 lg:my-6">
            <table className="min-w-[1120px] w-full text-left text-[13px]">
                <thead className="sticky top-0 z-20 bg-workbench text-[13px] font-semibold text-ink">
                    <tr>
                        <th className="w-14 whitespace-nowrap border-b border-ink/10 px-3 py-5">
                            <input type="checkbox" checked={allSelected} onChange={toggleAll} disabled={disabled || metrics.length === 0} aria-label="选择全部指标" className="h-5 w-5 accent-indigo" />
                        </th>
                        {["指标名称", "指标编码", "Cube", "口径摘要", "关系数量", "状态", "更新时间"].map((heading) => (
                            <th key={heading} className="whitespace-nowrap border-b border-ink/10 px-5 py-5 font-semibold">{heading}</th>
                        ))}
                        <th className="sticky right-0 z-10 whitespace-nowrap border-b border-l border-ink/10 bg-workbench px-5 py-5 font-semibold shadow-[-10px_0_18px_rgba(27,52,76,0.06)]">操作</th>
                    </tr>
                </thead>
                <tbody>
                    {loading ? (
                        <tr><td colSpan={9} className="px-5 py-14 text-center text-[13px] text-ink/45">正在加载指标建设数据...</td></tr>
                    ) : error ? (
                        <tr><td colSpan={9} role="alert" className="px-5 py-14 text-center text-[13px] text-oxide">{error}</td></tr>
                    ) : metrics.length === 0 ? (
                        <tr><td colSpan={9} className="px-5 py-14 text-center text-[13px] text-ink/45">暂无指标，请从工具栏新增指标。</td></tr>
                    ) : pageItems.map((member) => {
                        const title = emptyValue(member.title || member.member_name);
                        return (
                            <tr key={member.member_id} className="border-b border-ink/10 last:border-b-0 hover:bg-workbench/20">
                                <td className="px-3 py-6"><input type="checkbox" checked={selectedIds.includes(member.member_id)} onChange={(event) => onSelectionChange(member.member_id, event.target.checked)} disabled={disabled} aria-label={`选择指标 ${title}`} className="h-5 w-5 accent-indigo" /></td>
                                <td className="px-5 py-6 font-medium text-ink">{title}</td>
                                <td className="px-5 py-6 font-mono text-xs text-ink/65">{emptyValue(member.member_name)}</td>
                                <td className="px-5 py-6 text-ink/65">{emptyValue(member.cube_name)}</td>
                                <td className="max-w-xs px-5 py-6 text-ink/60">{emptyValue(member.calculation_note)}</td>
                                <td className="px-5 py-6 text-ink/60">–</td>
                                <td className="px-5 py-6 text-ink/65">{emptyValue(member.status)}</td>
                                <td className="px-5 py-6 text-ink/45">–</td>
                                <td className="sticky right-0 z-[1] bg-white px-5 py-6 shadow-[-10px_0_18px_rgba(27,52,76,0.06)]">
                                    <div className="flex items-center gap-3">
                                        <button type="button" onClick={(event) => onEdit(member.member_id, event.currentTarget)} disabled={disabled} title="编辑指标" aria-label={`编辑指标 ${title}`} className="text-indigo transition hover:text-cinnabar disabled:cursor-not-allowed disabled:opacity-40">编辑</button>
                                        <button type="button" onClick={(event) => onDelete(member.member_id, event.currentTarget)} disabled={disabled} title="删除指标" aria-label={`删除指标 ${title}`} className="text-oxide transition hover:text-cinnabar disabled:cursor-not-allowed disabled:opacity-40">删除</button>
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
                <tfoot>
                    <tr>
                        <td colSpan={9} className="border-t border-ink/10 px-5 py-3">
                            <div className="flex items-center justify-between gap-3 text-xs text-ink/50">
                                <span>共 {metrics.length} 条 · 每页 10 条</span>
                                <div className="flex items-center gap-2">
                                    <button type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1} className="px-2 py-1 text-ink/60 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-35" aria-label="上一页">上一页</button>
                                    <span className="min-w-16 text-center">第 {page} / {pageCount} 页</span>
                                    <button type="button" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={page === pageCount} className="px-2 py-1 text-ink/60 hover:bg-paper disabled:cursor-not-allowed disabled:opacity-35" aria-label="下一页">下一页</button>
                                </div>
                            </div>
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    );
}
