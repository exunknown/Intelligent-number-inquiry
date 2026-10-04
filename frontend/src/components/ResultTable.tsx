/**
 * 查询结果表格组件
 * 将后端返回的结构化数据归一化为数据看板卡片
 */
import {
    ArrowDown,
    ArrowUp,
    ArrowUpDown,
    Database,
    Download,
    Filter,
    Maximize2,
    Minimize2,
} from "lucide-react";
import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { downloadQueryExport } from "../lib/agentApi";
import { cn } from "../lib/format";
import { visibleMetricColumns } from "../lib/metricDisplay";
import type { MetricItem, QueryMode } from "../types/agent";

type SortState = {
    column: string;
    direction: "asc" | "desc";
} | null;

type DrillState = {
    column: string;
    value: string;
} | null;

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

function cellSearchValue(value: unknown) {
    return formatCell(value).trim();
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

function compareValues(
    left: unknown,
    right: unknown,
    numeric: boolean,
    direction: "asc" | "desc",
) {
    const modifier = direction === "asc" ? 1 : -1;
    if (numeric) {
        const leftNumber = Number(left);
        const rightNumber = Number(right);
        const leftValid = Number.isFinite(leftNumber);
        const rightValid = Number.isFinite(rightNumber);
        if (leftValid && rightValid) return (leftNumber - rightNumber) * modifier;
        if (leftValid) return -1 * modifier;
        if (rightValid) return 1 * modifier;
    }
    return cellSearchValue(left).localeCompare(cellSearchValue(right), "zh-Hans-CN") * modifier;
}

function sourceLabel(source?: QueryMode, verified?: boolean, warning?: string | null) {
    if (verified === true) return "数据来源：指标平台口径";
    if (verified === false) {
        return `数据来源：智能 SQL${warning ? `，${warning}` : "，需人工核对"}`;
    }
    return source === "metric" ? "数据来源：指标平台口径" : "数据来源：当前问数结果";
}

export function ResultTable({
    data,
    source,
    verified,
    warning,
    exportId,
    rowCount,
    truncated,
    metrics = [],
    hiddenAttachedMetricIds = new Set(),
}: {
    data: unknown;
    source?: QueryMode;
    verified?: boolean;
    warning?: string | null;
    exportId?: string;
    rowCount?: number;
    truncated?: boolean;
    metrics?: MetricItem[];
    hiddenAttachedMetricIds?: ReadonlySet<string>;
}) {
    const [downloading, setDownloading] = useState(false);
    const [downloadError, setDownloadError] = useState<string | null>(null);
    const [sortState, setSortState] = useState<SortState>(null);
    const [filterColumn, setFilterColumn] = useState<string>("");
    const [activeDrill, setActiveDrill] = useState<DrillState>(null);
    const [expanded, setExpanded] = useState(false);
    const [expandedPlaceholderHeight, setExpandedPlaceholderHeight] = useState<number | null>(null);
    const cardRef = useRef<HTMLElement | null>(null);
    const rows = normalizeRows(data);
    const allColumns = Array.from(
        rows.reduce((keys, row) => {
            Object.keys(row).forEach((key) => keys.add(key));
            return keys;
        }, new Set<string>()),
    );
    const columns = visibleMetricColumns(allColumns, metrics, hiddenAttachedMetricIds);

    if (columns.length === 0) {
        return null;
    }

    const numericColumns = new Set(columns.filter((column) => isNumericColumn(rows, column)));
    const selectedFilterColumn = columns.includes(filterColumn) ? filterColumn : columns[0];
    const drillSourceColumns = columns.filter((column) => !numericColumns.has(column));
    const drillColumn = drillSourceColumns.includes(selectedFilterColumn)
        ? selectedFilterColumn
        : drillSourceColumns[0] ?? selectedFilterColumn;
    const drillTags = Array.from(
        new Set(
            rows
                .map((row) => cellSearchValue(row[drillColumn]))
                .filter((value) => value && value !== "-"),
        ),
    ).slice(0, 8);
    const filteredRows = activeDrill
        ? rows.filter((row) => cellSearchValue(row[activeDrill.column]) === activeDrill.value)
        : rows;
    const displayRows = sortState
        ? [...filteredRows].sort((left, right) =>
              compareValues(
                  left[sortState.column],
                  right[sortState.column],
                  numericColumns.has(sortState.column),
                  sortState.direction,
              ),
          )
        : filteredRows;

    const toggleSort = (column: string) => {
        setSortState((current) => {
            if (current?.column !== column) return { column, direction: "asc" };
            if (current.direction === "asc") return { column, direction: "desc" };
            return null;
        });
    };

    const selectFilterColumn = (column: string) => {
        setFilterColumn(column);
        setActiveDrill(null);
    };

    const toggleExpanded = () => {
        if (!expanded) {
            const height = cardRef.current?.getBoundingClientRect().height;
            if (height) setExpandedPlaceholderHeight(height);
        } else {
            setExpandedPlaceholderHeight(null);
        }
        setExpanded((current) => !current);
    };

    const download = async () => {
        if (!exportId || downloading) return;
        setDownloading(true);
        setDownloadError(null);
        try {
            const blob = await downloadQueryExport(exportId);
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = `${exportId}.json`;
            anchor.click();
            URL.revokeObjectURL(url);
        } catch (error) {
            setDownloadError(error instanceof Error ? error.message : "结果下载失败");
        } finally {
            setDownloading(false);
        }
    };

    const card = (
        <section
            ref={cardRef}
            className={cn(
                "overflow-hidden rounded-2xl border border-ink/10 bg-white shadow-line",
                expanded && "fixed inset-0 z-50 flex h-dvh w-dvw flex-col rounded-none border-0",
            )}
            aria-labelledby="dashboard-result-title"
        >
            <div className="flex items-center justify-between gap-4 border-b border-ink/10 px-4 py-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2 font-serif text-sm font-bold text-ink">
                        <Database className="h-4 w-4 text-indigo" aria-hidden="true" />
                        <span id="dashboard-result-title">查询结果</span>
                    </div>
                    <div className="mt-1 text-xs text-ink/45">
                        当前展示 <span className="font-mono">{displayRows.length}</span> 行
                        {activeDrill && (
                            <span>
                                ，已下钻 {activeDrill.column}：{activeDrill.value}
                            </span>
                        )}
                    </div>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-xs text-ink/55">
                    <label className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-ink/10 bg-paper px-2">
                        <Filter className="h-3.5 w-3.5 text-indigo" aria-hidden="true" />
                        <span className="sr-only">筛选字段</span>
                        <select
                            value={selectedFilterColumn}
                            onChange={(event) => selectFilterColumn(event.target.value)}
                            className="max-w-36 bg-transparent text-xs font-medium text-ink outline-none"
                            aria-label="筛选字段"
                        >
                            {columns.map((column) => (
                                <option key={column} value={column}>
                                    {column}
                                </option>
                            ))}
                        </select>
                    </label>
                    <button
                        type="button"
                        onClick={toggleExpanded}
                        className={cn(
                            "grid h-9 w-9 place-items-center rounded-lg border border-ink/10 text-ink/65 transition hover:bg-white hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40",
                            expanded ? "bg-white shadow-line" : "bg-paper",
                        )}
                        title={expanded ? "退出全屏" : "全屏查看"}
                        aria-label={expanded ? "退出全屏" : "全屏查看"}
                    >
                        {expanded ? (
                            <Minimize2 className="h-4 w-4" aria-hidden="true" />
                        ) : (
                            <Maximize2 className="h-4 w-4" aria-hidden="true" />
                        )}
                    </button>
                    {exportId && (
                        <button
                            type="button"
                            onClick={download}
                            disabled={downloading}
                            title={downloading ? "正在下载" : "下载完整结果"}
                            aria-label={downloading ? "正在下载" : "下载完整结果"}
                            className="grid h-9 w-9 place-items-center rounded-lg border border-ink/10 bg-paper text-indigo transition hover:bg-white disabled:cursor-wait disabled:opacity-50"
                        >
                            <Download className="h-4 w-4" aria-hidden="true" />
                        </button>
                    )}
                </div>
            </div>
            {downloadError && <div className="border-b border-oxide/20 bg-oxide/5 px-4 py-2 text-xs text-oxide">{downloadError}</div>}
            <div className={cn("overflow-auto", expanded ? "min-h-0 flex-1" : "max-h-[420px]")}>
                <table className="min-w-full border-separate border-spacing-0 text-center text-sm">
                    <thead className="sticky top-0 z-10">
                        <tr>
                            {columns.map((column) => (
                                <th
                                    key={column}
                                    scope="col"
                                    className={cn(
                                        "border-b border-ink/10 bg-[#EFF1F3] px-4 py-3 font-semibold text-ink/65",
                                        sortState?.column === column && "text-ink",
                                    )}
                                >
                                    <button
                                        type="button"
                                        onClick={() => toggleSort(column)}
                                        className="mx-auto inline-flex min-h-8 items-center justify-center gap-1 rounded-md px-1 transition hover:bg-white/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/35"
                                        aria-label={`按 ${column} 排序`}
                                    >
                                        <span>{column}</span>
                                        {sortState?.column === column ? (
                                            sortState.direction === "asc" ? (
                                                <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                                            ) : (
                                                <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                                            )
                                        ) : (
                                            <ArrowUpDown className="h-3.5 w-3.5 text-ink/30" aria-hidden="true" />
                                        )}
                                    </button>
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {displayRows.length > 0 ? (
                            displayRows.map((row, rowIndex) => (
                                <tr key={rowIndex} className="odd:bg-white even:bg-[#F7F9FA]">
                                    {columns.map((column) => (
                                        <td
                                            key={column}
                                            className={cn(
                                                "border-b border-ink/5 px-4 py-3 text-center text-ink/80",
                                                numericColumns.has(column) && "tabular-nums",
                                            )}
                                        >
                                            {formatCell(row[column])}
                                        </td>
                                    ))}
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan={columns.length} className="px-4 py-10 text-center text-sm text-ink/45">
                                    当前筛选条件下暂无数据
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
            <div className="border-t border-ink/10 px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold text-ink/55">快捷下钻</span>
                    {drillTags.length > 0 ? (
                        drillTags.map((value) => {
                            const active =
                                activeDrill?.column === drillColumn && activeDrill.value === value;
                            return (
                                <button
                                    key={`${drillColumn}-${value}`}
                                    type="button"
                                    onClick={() =>
                                        setActiveDrill(active ? null : { column: drillColumn, value })
                                    }
                                    className={cn(
                                        "min-h-8 rounded-full border px-3 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/35",
                                        active
                                            ? "border-indigo bg-indigo text-white"
                                            : "border-ink/10 bg-paper text-ink/65 hover:border-indigo/30 hover:bg-indigo/5 hover:text-indigo",
                                    )}
                                >
                                    {value}
                                </button>
                            );
                        })
                    ) : (
                        <span className="text-xs text-ink/40">暂无可下钻字段</span>
                    )}
                    {activeDrill && (
                        <button
                            type="button"
                            onClick={() => setActiveDrill(null)}
                            className="min-h-8 rounded-full px-3 text-xs font-medium text-ink/50 transition hover:bg-ink/5 hover:text-ink"
                        >
                            清除下钻
                        </button>
                    )}
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-ink/45">
                    <span>{sourceLabel(source, verified, warning)}</span>
                    <span className="tabular-nums">
                        共 {rowCount ?? rows.length} 行{truncated ? "（当前为预览）" : ""}
                    </span>
                </div>
                </div>
        </section>
    );

    return (
        <div
            className="mt-5"
            style={
                expandedPlaceholderHeight
                    ? { minHeight: `${expandedPlaceholderHeight}px` }
                    : undefined
            }
        >
            {!expanded && card}
            {expanded &&
                typeof document !== "undefined" &&
                createPortal(card, document.body)}
        </div>
    );
}
