import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { X } from "lucide-react";
import type { SemanticCube, SemanticJoin } from "../lib/semanticModel";
import { nextFocusableIndex } from "../lib/userManagement";

export type JoinEditDialogProps = {
    mode: "create" | "edit";
    join: SemanticJoin;
    cubes: SemanticCube[];
    disabled: boolean;
    error: string | null;
    onCancel: () => void;
    onSave: (join: SemanticJoin) => void;
    onChange: (join: SemanticJoin) => void;
};

const RELATIONSHIPS = [
    ["many_to_one", "多对一"],
    ["one_to_many", "一对多"],
    ["one_to_one", "一对一"],
    ["many_to_many", "多对多"],
] as const;

const DIALOG_FOCUSABLE_SELECTOR = [
    "button:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

export function JoinEditDialog({
    mode,
    join,
    cubes,
    disabled,
    error,
    onCancel,
    onSave,
    onChange,
}: JoinEditDialogProps) {
    const dialogRef = useRef<HTMLDivElement | null>(null);
    const initialJoinRef = useRef(structuredClone(join));
    const hasChanges = JSON.stringify(initialJoinRef.current) !== JSON.stringify(join);
    const relationshipError = !join.relationship.trim()
        ? "Join 关系类型不能为空"
        : !RELATIONSHIPS.some(([value]) => value === join.relationship)
          ? "Join 关系类型不受支持"
          : null;

    useEffect(() => {
        dialogRef.current?.querySelector<HTMLElement>(DIALOG_FOCUSABLE_SELECTOR)?.focus();
    }, []);

    const handleCancel = () => {
        if (hasChanges && !window.confirm("当前 Join 编辑尚未保存，确定放弃修改吗？")) return;
        onCancel();
    };

    const handleDialogKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
        if (event.key === "Escape") {
            event.preventDefault();
            handleCancel();
            return;
        }
        if (event.key !== "Tab") return;
        const focusableElements = Array.from(
            dialogRef.current?.querySelectorAll<HTMLElement>(DIALOG_FOCUSABLE_SELECTOR) ?? [],
        );
        if (focusableElements.length === 0) return;
        const currentIndex = focusableElements.indexOf(document.activeElement as HTMLElement);
        const normalizedIndex = currentIndex === -1 ? (event.shiftKey ? 0 : -1) : currentIndex;
        event.preventDefault();
        focusableElements[
            nextFocusableIndex(
                normalizedIndex,
                focusableElements.length,
                event.shiftKey ? "backward" : "forward",
            )
        ]?.focus();
    };

    const update = <K extends keyof SemanticJoin>(key: K, value: SemanticJoin[K]) => {
        onChange({ ...join, [key]: value });
    };

    return (
        <div className="fixed inset-0 z-30 grid place-items-center bg-ink/20 p-6 backdrop-blur-[2px]" role="presentation">
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="join-edit-dialog-title"
                className="w-full max-w-2xl rounded-2xl bg-white shadow-line"
                onKeyDown={handleDialogKeyDown}
            >
                <header className="flex items-start justify-between gap-6 border-b border-ink/10 px-8 py-6">
                    <div>
                        <p id="join-edit-dialog-title" className="font-serif text-xl font-bold text-ink">
                            {mode === "create" ? "新增 Join" : "编辑 Join"}
                        </p>
                        <p className="mt-1 font-mono text-xs text-ink/45">
                            {mode === "create" ? "CREATE" : `${join.cube_name}->${join.target_cube_name}`}
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={handleCancel}
                        disabled={disabled}
                        title="关闭 Join 编辑弹窗"
                        aria-label="关闭 Join 编辑弹窗"
                        className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink/55 transition hover:bg-paper hover:text-ink disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                    >
                        <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                </header>
                <div className="grid gap-5 px-8 py-7">
                    <div className="grid grid-cols-2 gap-5">
                        <label className="text-sm font-semibold text-ink">
                            <span className="mb-2 block text-xs font-semibold text-ink/60">来源 Cube</span>
                            <select
                                value={join.cube_name}
                                onChange={(event) => update("cube_name", event.target.value)}
                                disabled={disabled}
                                required
                                className="h-11 w-full rounded-xl border border-ink/15 bg-paper px-4 text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-65"
                            >
                                <option value="">请选择来源 Cube</option>
                                {cubes.map((cube) => (
                                    <option key={cube.cube_name} value={cube.cube_name}>
                                        {cube.cube_name}{cube.title ? ` · ${cube.title}` : ""}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className="text-sm font-semibold text-ink">
                            <span className="mb-2 block text-xs font-semibold text-ink/60">目标 Cube</span>
                            <select
                                value={join.target_cube_name}
                                onChange={(event) => update("target_cube_name", event.target.value)}
                                disabled={disabled}
                                required
                                className="h-11 w-full rounded-xl border border-ink/15 bg-paper px-4 text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-65"
                            >
                                <option value="">请选择目标 Cube</option>
                                {cubes.map((cube) => (
                                    <option key={cube.cube_name} value={cube.cube_name}>
                                        {cube.cube_name}{cube.title ? ` · ${cube.title}` : ""}
                                    </option>
                                ))}
                            </select>
                        </label>
                    </div>
                    <label className="text-sm font-semibold text-ink">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">关系类型</span>
                        <select
                            value={join.relationship}
                            onChange={(event) => update("relationship", event.target.value)}
                            disabled={disabled}
                            required
                            aria-invalid={relationshipError ? "true" : undefined}
                            className="h-11 w-full rounded-xl border border-ink/15 bg-paper px-4 text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-65"
                        >
                            <option value="">请选择关系类型</option>
                            {RELATIONSHIPS.map(([value, label]) => (
                                <option key={value} value={value}>
                                    {label}（{value}）
                                </option>
                            ))}
                        </select>
                        {relationshipError && <span className="mt-2 block text-xs font-normal text-oxide">{relationshipError}</span>}
                    </label>
                    <label className="text-sm font-semibold text-ink">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">SQL 表达式</span>
                        <textarea
                            value={join.sql_expression}
                            onChange={(event) => update("sql_expression", event.target.value)}
                            disabled={disabled}
                            required
                            rows={5}
                            className="min-h-32 w-full rounded-xl border border-ink/15 bg-paper px-4 py-3 font-mono text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-65"
                        />
                    </label>
                </div>
                {error && <p role="alert" className="border-t border-oxide/20 bg-oxide/5 px-8 py-3 text-sm text-oxide">{error}</p>}
                <footer className="flex justify-end gap-3 border-t border-ink/10 bg-paper px-8 py-5">
                    <button type="button" onClick={handleCancel} disabled={disabled} className="min-h-11 rounded-xl border border-ink/15 px-5 text-sm font-semibold text-ink/65 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40">取消</button>
                    <button type="button" onClick={() => onSave({ ...join, editable: true })} disabled={disabled} className="min-h-11 rounded-xl bg-dai px-5 text-sm font-semibold text-paper transition hover:bg-dai/90 disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40">保存 Join</button>
                </footer>
            </div>
        </div>
    );
}
