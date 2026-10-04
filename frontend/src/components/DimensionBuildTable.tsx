import { useEffect, useState } from "react";
import type { SemanticMember } from "../lib/semanticModel";

export type DimensionBuildTableProps = {
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

export function DimensionBuildTable({
    items,
    loading,
    error,
    disabled,
    selectedIds,
    onSelectionChange,
    onEdit,
    onDelete,
}: DimensionBuildTableProps) {
    const dimensions = items.filter((member) => member.member_type === "dimension" || member.member_type === "time_dimension");
    const [page, setPage] = useState(1);
    const pageCount = Math.max(1, Math.ceil(dimensions.length / PAGE_SIZE));
    const itemKey = dimensions.map((member) => member.member_id).join("|");
    const pageItems = dimensions.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
    const allSelected = pageItems.length > 0 && pageItems.every((member) => selectedIds.includes(member.member_id));

    useEffect(() => {
        setPage(1);
    }, [itemKey]);

    const toggleAll = () => {
        pageItems.forEach((member) => onSelectionChange(member.member_id, !allSelected));
    };

    return (
        <div id="agent-panel-dimensions" role="tabpanel" aria-labelledby="agent-tab-dimensions" className="mx-8 my-5 min-h-0 max-h-[460px] overflow-auto overscroll-contain rounded-2xl border border-ink/15 bg-white shadow-line lg:mx-12 lg:my-6">
            <table className="min-w-[1400px] w-full text-left text-[13px]">
                <thead className="sticky top-0 z-20 bg-workbench text-[13px] font-semibold text-ink">
                    <tr>
                        <th className="w-14 whitespace-nowrap border-b border-ink/10 px-3 py-5">
                            <input type="checkbox" checked={allSelected} onChange={toggleAll} disabled={disabled || dimensions.length === 0} aria-label="选择全部维度" className="h-5 w-5 accent-indigo" />
                        </th>
                        {["维度名称", "维度编码", "Cube", "维度类型", "数据类型", "主键", "使用情况", "状态", "更新时间"].map((heading) => (
                            <th key={heading} className="whitespace-nowrap border-b border-ink/10 px-5 py-5 font-semibold">{heading}</th>
                        ))}
                        <th className="sticky right-0 z-10 whitespace-nowrap border-b border-l border-ink/10 bg-workbench px-5 py-5 font-semibold shadow-[-10px_0_18px_rgba(27,52,76,0.06)]">操作</th>
                    </tr>
                </thead>
                <tbody>
                    {loading ? (
                        <tr><td colSpan={11} className="px-5 py-14 text-center text-[13px] text-ink/45">正在加载维度建设数据...</td></tr>
                    ) : error ? (
                        <tr><td colSpan={11} role="alert" className="px-5 py-14 text-center text-[13px] text-oxide">{error}</td></tr>
                    ) : dimensions.length === 0 ? (
                        <tr><td colSpan={11} className="px-5 py-14 text-center text-[13px] text-ink/45">暂无维度，请从工具栏新增维度。</td></tr>
                    ) : pageItems.map((member) => {
                        const title = emptyValue(member.title || member.member_name);
                        return (
                            <tr key={member.member_id} className="border-b border-ink/10 last:border-b-0 hover:bg-workbench/20">
                                <td className="px-3 py-6"><input type="checkbox" checked={selectedIds.includes(member.member_id)} onChange={(event) => onSelectionChange(member.member_id, event.target.checked)} disabled={disabled} aria-label={`选择维度 ${title}`} className="h-5 w-5 accent-indigo" /></td>
                                <td className="px-5 py-6 font-medium text-ink">{title}</td>
                                <td className="px-5 py-6 font-mono text-xs text-ink/65">{emptyValue(member.member_name)}</td>
                                <td className="px-5 py-6 text-ink/65">{emptyValue(member.cube_name)}</td>
                                <td className="px-5 py-6 text-ink/65">{member.member_type === "time_dimension" ? "时间维度" : "维度"}</td>
                                <td className="px-5 py-6 text-ink/65">{emptyValue(member.data_type)}</td>
                                <td className="px-5 py-6 text-ink/60">{member.dimension?.primary_key ? "是" : "否"}</td>
                                <td className="px-5 py-6 text-ink/60">{member.filterable ? "可筛选" : "不可筛选"}</td>
                                <td className="px-5 py-6 text-ink/65">{emptyValue(member.status)}</td>
                                <td className="px-5 py-6 text-ink/45">–</td>
                                <td className="sticky right-0 z-[1] bg-white px-5 py-6 shadow-[-10px_0_18px_rgba(27,52,76,0.06)]">
                                    <div className="flex items-center gap-3">
                                        <button type="button" onClick={(event) => onEdit(member.member_id, event.currentTarget)} disabled={disabled} title="编辑维度" aria-label={`编辑维度 ${title}`} className="text-indigo transition hover:text-cinnabar disabled:cursor-not-allowed disabled:opacity-40">编辑</button>
                                        <button type="button" onClick={(event) => onDelete(member.member_id, event.currentTarget)} disabled={disabled} title="删除维度" aria-label={`删除维度 ${title}`} className="text-oxide transition hover:text-cinnabar disabled:cursor-not-allowed disabled:opacity-40">删除</button>
                                    </div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
                <tfoot>
                    <tr>
                        <td colSpan={11} className="border-t border-ink/10 px-5 py-3">
                            <div className="flex items-center justify-between gap-3 text-xs text-ink/50">
                                <span>共 {dimensions.length} 条 · 每页 10 条</span>
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
