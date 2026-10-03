import { Edit3, Trash2 } from "lucide-react";
import {
    canDeleteSemanticJoin,
    canEditSemanticJoin,
    type SemanticJoin,
} from "../lib/semanticModel";

export type JoinBuildTableProps = {
    items: SemanticJoin[];
    cubeTitles: Record<string, string>;
    loading: boolean;
    error: string | null;
    disabled: boolean;
    onEdit: (join: SemanticJoin, trigger: HTMLButtonElement) => void;
    onDelete: (join: SemanticJoin, trigger: HTMLButtonElement) => void;
};

const emptyValue = (value: string | null | undefined) => value || "–";

function cubeLabel(cubeName: string, cubeTitles: Record<string, string>): string {
    const title = cubeTitles[cubeName];
    return title ? `${cubeName} · ${title}` : cubeName;
}

export function JoinBuildTable({
    items,
    cubeTitles,
    loading,
    error,
    disabled,
    onEdit,
    onDelete,
}: JoinBuildTableProps) {
    return (
        <div
            id="agent-panel-joins"
            role="region"
            aria-labelledby="agent-panel-joins-title"
            className="mx-8 my-5 min-h-0 max-h-[460px] overflow-auto overscroll-contain rounded-2xl border border-ink/15 bg-white shadow-line lg:mx-12 lg:my-6"
        >
            <table className="min-w-[1120px] w-full text-left text-[13px]">
                <caption id="agent-panel-joins-title" className="sr-only">
                    Cube Join 管理
                </caption>
                <thead className="sticky top-0 z-20 bg-workbench text-[13px] font-semibold text-ink">
                    <tr>
                        {["来源 Cube", "目标 Cube", "关系类型", "SQL 表达式", "来源状态", "操作"].map(
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
                            <td colSpan={6} className="px-5 py-14 text-center text-[13px] text-ink/45">
                                正在加载 Join 建设数据...
                            </td>
                        </tr>
                    ) : error ? (
                        <tr>
                            <td colSpan={6} role="alert" className="px-5 py-14 text-center text-[13px] text-oxide">
                                {error}
                            </td>
                        </tr>
                    ) : items.length === 0 ? (
                        <tr>
                            <td colSpan={6} className="px-5 py-14 text-center text-[13px] text-ink/45">
                                暂无 Join，请新增来源 Cube 与目标 Cube 的关系。
                            </td>
                        </tr>
                    ) : (
                        items.map((join) => {
                            const canEdit = canEditSemanticJoin(join);
                            const canDelete = canDeleteSemanticJoin(join);
                            return (
                                <tr
                                    key={`${join.cube_name}->${join.target_cube_name}`}
                                    className="border-b border-ink/10 last:border-b-0 hover:bg-workbench/20"
                                >
                                    <td className="px-5 py-6 font-medium text-ink">
                                        {cubeLabel(join.cube_name, cubeTitles)}
                                    </td>
                                    <td className="px-5 py-6 font-medium text-ink">
                                        {cubeLabel(join.target_cube_name, cubeTitles)}
                                    </td>
                                    <td className="px-5 py-6 font-mono text-xs text-ink/65">
                                        {emptyValue(join.relationship)}
                                    </td>
                                    <td className="max-w-[420px] px-5 py-6 font-mono text-xs text-ink/65">
                                        <span className="block truncate" title={join.sql_expression}>
                                            {emptyValue(join.sql_expression)}
                                        </span>
                                    </td>
                                    <td className="px-5 py-6 text-ink/65">
                                        {canEdit ? "可编辑" : "只读"}
                                    </td>
                                    <td className="px-5 py-6">
                                        {canEdit || canDelete ? (
                                            <div className="flex items-center gap-3">
                                                {canEdit ? (
                                                    <button
                                                        type="button"
                                                        onClick={(event) => onEdit(join, event.currentTarget)}
                                                        disabled={disabled}
                                                        title="编辑 Join"
                                                        aria-label={`编辑 Join ${join.cube_name} 到 ${join.target_cube_name}`}
                                                        className="grid h-8 w-8 place-items-center rounded-full text-indigo transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"
                                                    >
                                                        <Edit3 className="h-4 w-4" aria-hidden="true" />
                                                    </button>
                                                ) : null}
                                                {canDelete ? (
                                                    <button
                                                        type="button"
                                                        onClick={(event) => onDelete(join, event.currentTarget)}
                                                        disabled={disabled}
                                                        title="删除 Join"
                                                        aria-label={`删除 Join ${join.cube_name} 到 ${join.target_cube_name}`}
                                                        className="grid h-8 w-8 place-items-center rounded-full text-oxide transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-40"
                                                    >
                                                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                                                    </button>
                                                ) : null}
                                            </div>
                                        ) : (
                                            <span className="text-xs text-ink/35">—</span>
                                        )}
                                    </td>
                                </tr>
                            );
                        })
                    )}
                </tbody>
            </table>
        </div>
    );
}
