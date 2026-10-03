import { Edit3, Trash2 } from "lucide-react";
import type { SemanticCube } from "../lib/semanticModel";

export type CubeBuildTableProps = {
    items: SemanticCube[];
    memberCounts: Record<string, number>;
    joinCounts: Record<string, number>;
    loading: boolean;
    error: string | null;
    disabled: boolean;
    onEdit: (cubeName: string, trigger: HTMLButtonElement) => void;
    onDelete: (cubeName: string, trigger: HTMLButtonElement) => void;
};

const emptyValue = (value: string | null | undefined) => value || "–";

export function CubeBuildTable({
    items,
    memberCounts,
    joinCounts,
    loading,
    error,
    disabled,
    onEdit,
    onDelete,
}: CubeBuildTableProps) {
    return (
        <div
            id="agent-panel-cubes"
            role="tabpanel"
            aria-labelledby="agent-tab-cubes"
            className="mx-8 my-5 min-h-0 max-h-[460px] overflow-auto overscroll-contain rounded-2xl border border-ink/15 bg-white shadow-line lg:mx-12 lg:my-6"
        >
            <table className="min-w-[1120px] w-full text-left text-[13px]">
                <thead className="sticky top-0 z-20 bg-workbench text-[13px] font-semibold text-ink">
                    <tr>
                        {["Cube 编码", "Cube 名称", "物理表", "公开状态", "成员数量", "Join 数量", "操作"].map(
                            (heading) => (
                                <th
                                    key={heading}
                                    className="whitespace-nowrap border-b border-ink/10 px-5 py-5 font-semibold"
                                >
                                    {heading}
                                </th>
                            ),
                        )}
                    </tr>
                </thead>
                <tbody>
                    {loading ? (
                        <tr>
                            <td colSpan={7} className="px-5 py-14 text-center text-[13px] text-ink/45">
                                正在加载 Cube 建设数据...
                            </td>
                        </tr>
                    ) : error ? (
                        <tr>
                            <td colSpan={7} role="alert" className="px-5 py-14 text-center text-[13px] text-oxide">
                                {error}
                            </td>
                        </tr>
                    ) : items.length === 0 ? (
                        <tr>
                            <td colSpan={7} className="px-5 py-14 text-center text-[13px] text-ink/45">
                                暂无 Cube，请从工具栏新增 Cube。
                            </td>
                        </tr>
                    ) : (
                        items.map((cube) => (
                            <tr key={cube.cube_name} className="border-b border-ink/10 last:border-b-0 hover:bg-workbench/20">
                                <td className="px-5 py-6 font-mono text-xs text-ink/70">{emptyValue(cube.cube_name)}</td>
                                <td className="px-5 py-6 font-medium text-ink">{emptyValue(cube.title)}</td>
                                <td className="px-5 py-6 font-mono text-xs text-ink/65">{emptyValue(cube.sql_table)}</td>
                                <td className="px-5 py-6 text-ink/65">{cube.public ? "公开" : "不公开"}</td>
                                <td className="px-5 py-6 text-ink/65">{memberCounts[cube.cube_name] ?? 0}</td>
                                <td className="px-5 py-6 text-ink/65">{joinCounts[cube.cube_name] ?? 0}</td>
                                <td className="px-5 py-6">
                                    <div className="flex items-center gap-3">
                                        <button
                                            type="button"
                                            onClick={(event) => onEdit(cube.cube_name, event.currentTarget)}
                                            disabled={disabled}
                                            title="编辑 Cube"
                                            aria-label={`编辑 Cube ${cube.cube_name}`}
                                            className="grid h-8 w-8 place-items-center rounded-full text-indigo transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"
                                        >
                                            <Edit3 className="h-4 w-4" aria-hidden="true" />
                                        </button>
                                        <button
                                            type="button"
                                            onClick={(event) => onDelete(cube.cube_name, event.currentTarget)}
                                            disabled={disabled}
                                            title="删除 Cube"
                                            aria-label={`删除 Cube ${cube.cube_name}`}
                                            className="grid h-8 w-8 place-items-center rounded-full text-oxide transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"
                                        >
                                            <Trash2 className="h-4 w-4" aria-hidden="true" />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}
