import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { X } from "lucide-react";
import type { SemanticCube } from "../lib/semanticModel";
import { nextFocusableIndex } from "../lib/userManagement";

export type CubeEditDialogProps = {
    mode: "create" | "edit";
    cube: SemanticCube;
    disabled: boolean;
    error: string | null;
    onCancel: () => void;
    onSave: (cube: SemanticCube) => void;
    onChange: (cube: SemanticCube) => void;
};

const DIALOG_FOCUSABLE_SELECTOR = [
    "button:not([disabled])",
    "input:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

export function CubeEditDialog({
    mode,
    cube,
    disabled,
    error,
    onCancel,
    onSave,
    onChange,
}: CubeEditDialogProps) {
    const dialogRef = useRef<HTMLDivElement | null>(null);
    const initialCubeRef = useRef(structuredClone(cube));
    const hasChanges = JSON.stringify(initialCubeRef.current) !== JSON.stringify(cube);

    const handleCancel = () => {
        if (hasChanges && !window.confirm("当前 Cube 编辑尚未保存，确定放弃修改吗？")) return;
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

    useEffect(() => {
        dialogRef.current?.querySelector<HTMLElement>(DIALOG_FOCUSABLE_SELECTOR)?.focus();
    }, []);

    const update = <K extends keyof SemanticCube>(key: K, value: SemanticCube[K]) => {
        onChange({ ...cube, [key]: value });
    };

    return (
        <div className="fixed inset-0 z-30 grid place-items-center bg-ink/20 p-6 backdrop-blur-[2px]" role="presentation">
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="cube-edit-dialog-title"
                className="w-full max-w-2xl rounded-2xl bg-white shadow-line"
                onKeyDown={handleDialogKeyDown}
            >
                <header className="flex items-start justify-between gap-6 border-b border-ink/10 px-8 py-6">
                    <div>
                        <p id="cube-edit-dialog-title" className="font-serif text-xl font-bold text-ink">
                            {mode === "create" ? "新增 Cube" : "编辑 Cube"}
                        </p>
                        <p className="mt-1 font-mono text-xs text-ink/45">
                            {mode === "create" ? "CREATE" : cube.cube_name}
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={handleCancel}
                        disabled={disabled}
                        title="关闭 Cube 编辑弹窗"
                        aria-label="关闭 Cube 编辑弹窗"
                        className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink/55 transition hover:bg-paper hover:text-ink disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                    >
                        <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                </header>
                <div className="grid gap-5 px-8 py-7">
                    <label className="text-sm font-semibold text-ink">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">Cube 编码</span>
                        <input
                            value={cube.cube_name}
                            onChange={(event) => update("cube_name", event.target.value)}
                            disabled={mode === "edit" || disabled}
                            required
                            className="h-11 w-full rounded-xl border border-ink/15 bg-paper px-4 font-mono text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:bg-ink/5 disabled:opacity-65"
                        />
                    </label>
                    <div className="grid grid-cols-2 gap-5">
                        <label className="text-sm font-semibold text-ink">
                            <span className="mb-2 block text-xs font-semibold text-ink/60">Cube 名称</span>
                            <input value={cube.title} onChange={(event) => update("title", event.target.value)} disabled={disabled} required className="h-11 w-full rounded-xl border border-ink/15 bg-paper px-4 text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-65" />
                        </label>
                        <label className="text-sm font-semibold text-ink">
                            <span className="mb-2 block text-xs font-semibold text-ink/60">物理表</span>
                            <input value={cube.sql_table} onChange={(event) => update("sql_table", event.target.value)} disabled={disabled} required className="h-11 w-full rounded-xl border border-ink/15 bg-paper px-4 font-mono text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-65" />
                        </label>
                    </div>
                    <label className="text-sm font-semibold text-ink">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">描述</span>
                        <textarea value={cube.description} onChange={(event) => update("description", event.target.value)} disabled={disabled} rows={4} className="min-h-28 w-full rounded-xl border border-ink/15 bg-paper px-4 py-3 text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-65" />
                    </label>
                    <label className="inline-flex items-center gap-3 text-sm font-semibold text-ink">
                        <input type="checkbox" checked={cube.public} onChange={(event) => update("public", event.target.checked)} disabled={disabled} className="h-5 w-5 accent-indigo" />
                        公开 Cube
                    </label>
                </div>
                {error && <p role="alert" className="border-t border-oxide/20 bg-oxide/5 px-8 py-3 text-sm text-oxide">{error}</p>}
                <footer className="flex justify-end gap-3 border-t border-ink/10 bg-paper px-8 py-5">
                    <button type="button" onClick={handleCancel} disabled={disabled} className="min-h-11 rounded-xl border border-ink/15 px-5 text-sm font-semibold text-ink/65 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40">取消</button>
                    <button type="button" onClick={() => onSave(cube)} disabled={disabled} className="min-h-11 rounded-xl bg-dai px-5 text-sm font-semibold text-paper transition hover:bg-dai/90 disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40">保存 Cube</button>
                </footer>
            </div>
        </div>
    );
}
