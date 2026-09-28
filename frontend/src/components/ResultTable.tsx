/**
 * 查询结果表格组件
 * 将后端返回的结构化数据归一化为可滚动报表（黛蓝表头，数值列右对齐）
 */
import { Database, FileJson } from "lucide-react";
import { cn } from "../lib/format";

function normalizeRows(data: unknown): Array<Record<string, unknown>> {
    if (Array.isArray(data)) {
        return data.map((item, index) =>
            item && typeof item === "object" && !Array.isArray(item)
                ? (item as Record<string, unknown>)
                : { 序号: index + 1, 值: item },
        );
    }

    if (data && typeof data === "object") {
        return [data as Record<string, unknown>];
    }

    return [{ 值: data ?? "" }];
}

function formatCell(value: unknown) {
    if (value === null || value === undefined) return "-";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
}

/** 数值列判定：列内非空值全是有限数字或可转数字的字符串 */
function isNumericColumn(rows: Array<Record<string, unknown>>, column: string) {
    let seen = false;
    for (const row of rows) {
        const value = row[column];
        if (value === null || value === undefined || value === "") continue;
        seen = true;
        if (typeof value === "number") {
            if (!Number.isFinite(value)) return false;
            continue;
        }
        if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
            continue;
        }
        return false;
    }
    return seen;
}

export function ResultTable({ data }: { data: unknown }) {
    const rows = normalizeRows(data);
    const columns = Array.from(
        rows.reduce((keys, row) => {
            Object.keys(row).forEach((key) => keys.add(key));
            return keys;
        }, new Set<string>()),
    );

    if (columns.length === 0) {
        return null;
    }

    const numericColumns = new Set(columns.filter((column) => isNumericColumn(rows, column)));

    return (
        <section className="mt-4 overflow-hidden rounded-xl border border-ink/15 bg-white">
            <div className="flex items-center justify-between border-b border-ink/10 px-4 py-3">
                <div className="flex items-center gap-2 font-serif text-sm font-bold text-ink">
                    <Database className="h-4 w-4 text-indigo" aria-hidden="true" />
                    查询结果
                </div>
                <div className="flex items-center gap-2 text-xs text-ink/55">
                    <FileJson className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="tabular-nums">{rows.length} 行</span>
                </div>
            </div>
            <div className="max-h-[360px] overflow-auto">
                <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
                    <thead className="sticky top-0 z-10">
                        <tr>
                            {columns.map((column) => (
                                <th
                                    key={column}
                                    scope="col"
                                    className={cn(
                                        "border-b border-dai bg-dai px-4 py-3 font-medium text-paper/90",
                                        numericColumns.has(column) && "text-right",
                                    )}
                                >
                                    {column}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, rowIndex) => (
                            <tr key={rowIndex} className="odd:bg-white even:bg-paper/70">
                                {columns.map((column) => (
                                    <td
                                        key={column}
                                        className={cn(
                                            "border-b border-ink/5 px-4 py-3 text-ink/80",
                                            numericColumns.has(column) && "text-right tabular-nums",
                                        )}
                                    >
                                        {formatCell(row[column])}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
