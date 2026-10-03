import {
    CheckCircle2,
    RotateCcw,
    Save,
    Send,
    ShieldCheck,
    Upload,
    XCircle,
} from "lucide-react";
import { useState } from "react";
import type { SemanticRelease } from "../lib/semanticModel";

type SemanticVersionActionBarProps = {
    releases: SemanticRelease[];
    draftStatus: string | null;
    dirty: boolean;
    busy: boolean;
    canReview: boolean;
    canPublish: boolean;
    canRollback: boolean;
    hasValidationErrors: boolean;
    onSave: () => void;
    onValidate: () => void;
    onSubmit: () => void;
    onReview: (decision: "approved" | "rejected") => void;
    onPublish: () => void;
    onRollback: (release: SemanticRelease) => void;
};

export function SemanticVersionActionBar({
    releases,
    draftStatus,
    dirty,
    busy,
    canReview,
    canPublish,
    canRollback,
    hasValidationErrors,
    onSave,
    onValidate,
    onSubmit,
    onReview,
    onPublish,
    onRollback,
}: SemanticVersionActionBarProps) {
    const [rollbackVersion, setRollbackVersion] = useState("");
    const activeReleaseVersion = releases.find((release) => release.active)?.release_version;
    const rollbackReleases = releases.filter(
        (release) => !release.active && release.release_version !== activeReleaseVersion,
    );
    const selectedRelease = rollbackReleases.find(
        (release) => release.release_version === rollbackVersion,
    );

    return (
        <section className="sticky bottom-0 z-10 border-t border-ink/15 bg-white/95 px-5 py-3 shadow-line backdrop-blur lg:px-7" aria-label="语义模型版本操作">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3 text-xs text-ink/55">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${dirty ? "bg-cinnabar" : "bg-pine"}`} aria-hidden="true" />
                    <span>{dirty ? "有未保存修改" : draftStatus ? `草稿状态：${draftStatus}` : "暂无草稿"}</span>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                    <button type="button" onClick={onSave} disabled={busy || !dirty} className="inline-flex min-h-9 items-center gap-2 border border-ink/15 px-3 text-xs font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-45" title="保存草稿">
                        <Save className="h-4 w-4" aria-hidden="true" />保存草稿
                    </button>
                    <button type="button" onClick={onValidate} disabled={busy} className="inline-flex min-h-9 items-center gap-2 border border-ink/15 px-3 text-xs font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-45">
                        <ShieldCheck className="h-4 w-4" aria-hidden="true" />校验
                    </button>
                    <button type="button" onClick={onSubmit} disabled={busy || !draftStatus || draftStatus !== "draft" || hasValidationErrors} className="inline-flex min-h-9 items-center gap-2 bg-indigo px-3 text-xs font-semibold text-paper transition hover:bg-dai disabled:cursor-not-allowed disabled:opacity-45">
                        <Send className="h-4 w-4" aria-hidden="true" />提交审核
                    </button>
                    {canReview && <>
                        <button type="button" onClick={() => onReview("approved")} disabled={busy} className="inline-flex min-h-9 items-center gap-2 bg-pine px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">
                            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />通过
                        </button>
                        <button type="button" onClick={() => onReview("rejected")} disabled={busy} className="inline-flex min-h-9 items-center gap-2 border border-oxide/30 px-3 text-xs font-semibold text-oxide disabled:cursor-not-allowed disabled:opacity-45">
                            <XCircle className="h-4 w-4" aria-hidden="true" />驳回
                        </button>
                    </>}
                    <button type="button" onClick={onPublish} disabled={busy || !canPublish} className="inline-flex min-h-9 items-center gap-2 bg-cinnabar px-3 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45">
                        <Upload className="h-4 w-4" aria-hidden="true" />发布版本
                    </button>
                    <div className="flex items-center gap-2 border-l border-ink/10 pl-2">
                        <select value={rollbackVersion} onChange={(event) => setRollbackVersion(event.target.value)} disabled={busy || dirty || !canRollback || rollbackReleases.length === 0} aria-label="选择回滚版本" className="h-9 max-w-44 border border-ink/15 bg-white px-2 text-xs text-ink outline-none focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-45">
                            <option value="">选择回滚版本</option>
                            {rollbackReleases.map((release) => <option key={release.release_version} value={release.release_version}>{release.release_version}</option>)}
                        </select>
                        <button type="button" onClick={() => selectedRelease && onRollback(selectedRelease)} disabled={busy || dirty || !canRollback || !selectedRelease} className="inline-flex min-h-9 items-center gap-2 border border-oxide/30 px-3 text-xs font-semibold text-oxide hover:bg-oxide/5 disabled:cursor-not-allowed disabled:opacity-45" title="请求回滚">
                            <RotateCcw className="h-4 w-4" aria-hidden="true" />回滚
                        </button>
                    </div>
                </div>
            </div>
        </section>
    );
}
