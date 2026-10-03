import { X } from "lucide-react";
import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";
import {
    type SemanticMember,
    type SemanticMetricAttachment,
    type SemanticMetricEquivalenceGroup,
    type SemanticSnapshot,
    semanticMemberDialogHasChanges,
    validateSemanticMemberName,
} from "../lib/semanticModel";
import { nextFocusableIndex } from "../lib/userManagement";
import { SemanticMemberEditor } from "./SemanticMemberEditor";

export type SemanticMemberEditDialogProps = {
    mode: "create" | "edit" | "copy";
    member: SemanticMember | null;
    snapshot: SemanticSnapshot;
    members: SemanticMember[];
    dependencyCandidates: SemanticMember[];
    metricEquivalenceGroups: SemanticMetricEquivalenceGroup[];
    metricAttachments: SemanticMetricAttachment[];
    disabled: boolean;
    error?: string | null;
    onCancel: () => void;
    onSave: () => void;
    onChange: (member: SemanticMember) => void;
    onMemberNameChange: (memberName: string) => void;
    onRelationsChange: (
        groups: SemanticMetricEquivalenceGroup[],
        attachments: SemanticMetricAttachment[],
    ) => void;
};

const DIALOG_FOCUSABLE_SELECTOR = [
    "button:not([disabled])",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

function memberTypeLabel(member: SemanticMember): string {
    return member.member_type === "measure"
        ? "指标"
        : member.member_type === "time_dimension"
          ? "时间维度"
          : "维度";
}

function dialogTitle(mode: SemanticMemberEditDialogProps["mode"], member: SemanticMember): string {
    const action = mode === "create" ? "新增" : mode === "copy" ? "复制" : "编辑";
    return `${action}${memberTypeLabel(member)}`;
}

export function SemanticMemberEditDialog({
    mode,
    member,
    snapshot,
    members,
    dependencyCandidates,
    metricEquivalenceGroups,
    metricAttachments,
    disabled,
    error,
    onCancel,
    onSave,
    onChange,
    onMemberNameChange,
    onRelationsChange,
}: SemanticMemberEditDialogProps) {
    const dialogRef = useRef<HTMLDivElement | null>(null);
    const initialMemberRef = useRef(member ? structuredClone(member) : null);
    const initialMetricEquivalenceGroupsRef = useRef(structuredClone(metricEquivalenceGroups));
    const initialMetricAttachmentsRef = useRef(structuredClone(metricAttachments));
    const memberNameError = member
        ? validateSemanticMemberName(snapshot, member, member.member_name)
        : null;
    const hasChanges = semanticMemberDialogHasChanges(
        initialMemberRef.current,
        member,
        initialMetricEquivalenceGroupsRef.current,
        metricEquivalenceGroups,
        initialMetricAttachmentsRef.current,
        metricAttachments,
    );

    const handleCancel = () => {
        if (hasChanges && !window.confirm("当前成员编辑尚未保存，确定放弃修改吗？")) return;
        onCancel();
    };

    const handleSave = () => {
        if (memberNameError) return;
        onSave();
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
        const targetIndex = nextFocusableIndex(
            normalizedIndex,
            focusableElements.length,
            event.shiftKey ? "backward" : "forward",
        );
        event.preventDefault();
        focusableElements[targetIndex]?.focus();
    };

    useEffect(() => {
        const firstFocusable = dialogRef.current?.querySelector<HTMLElement>(DIALOG_FOCUSABLE_SELECTOR);
        firstFocusable?.focus();
    }, []);

    if (!member) return null;

    return (
        <div className="fixed inset-0 z-30 grid place-items-center bg-ink/20 p-6" role="presentation">
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="semantic-member-dialog-title"
                className="flex max-h-[calc(100vh-3rem)] w-full max-w-5xl flex-col overflow-hidden bg-white shadow-line"
                onKeyDown={handleDialogKeyDown}
            >
                <header className="flex shrink-0 items-start justify-between gap-6 border-b border-ink/10 bg-white px-6 py-5">
                    <div>
                        <p id="semantic-member-dialog-title" className="font-serif text-xl font-bold text-ink">
                            {dialogTitle(mode, member)}
                        </p>
                        <p className="mt-1 font-mono text-xs text-ink/45">
                            {member.cube_name} / {member.member_name}
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={handleCancel}
                        disabled={disabled}
                        title="关闭编辑弹窗"
                        aria-label="关闭编辑弹窗"
                        className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink/55 transition hover:bg-paper hover:text-ink disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50"
                    >
                        <X className="h-4 w-4" aria-hidden="true" />
                    </button>
                </header>
                <div className="min-h-0 flex-1 overflow-y-auto">
                    <SemanticMemberEditor
                        member={member}
                        snapshot={snapshot}
                        members={members}
                        dependencyCandidates={dependencyCandidates}
                        metricEquivalenceGroups={metricEquivalenceGroups}
                        metricAttachments={metricAttachments}
                        disabled={disabled}
                        onChange={onChange}
                        onMemberNameChange={onMemberNameChange}
                        onRelationsChange={onRelationsChange}
                        showActions={false}
                    />
                </div>
                {(error || memberNameError) && <p role="alert" className="shrink-0 border-t border-oxide/20 bg-oxide/5 px-6 py-3 text-sm text-oxide">{error || memberNameError}</p>}
                <footer className="flex shrink-0 justify-end gap-3 border-t border-ink/10 bg-paper px-6 py-4">
                    <button
                        type="button"
                        onClick={handleCancel}
                        disabled={disabled}
                        className="min-h-10 border border-ink/15 px-4 text-sm font-semibold text-ink/65 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                    >
                        取消
                    </button>
                    <button
                        type="button"
                        onClick={handleSave}
                        disabled={disabled || Boolean(memberNameError)}
                        className="min-h-10 bg-dai px-4 text-sm font-semibold text-paper transition hover:bg-dai/90 disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                    >
                        保存成员
                    </button>
                </footer>
            </div>
        </div>
    );
}
