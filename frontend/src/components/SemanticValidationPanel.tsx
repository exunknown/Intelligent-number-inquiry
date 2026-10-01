import { CheckCircle2, CircleAlert, Send, ShieldCheck, XCircle } from "lucide-react";
import type { SemanticValidationIssue } from "../lib/semanticModel";

type SemanticValidationPanelProps = {
    issues: SemanticValidationIssue[];
    status: string | null;
    canReview: boolean;
    canPublish: boolean;
    busy: boolean;
    onValidate: () => void;
    onSubmit: () => void;
    onReview: (decision: "approved" | "rejected") => void;
    onPublish: () => void;
};

export function SemanticValidationPanel({ issues, status, canReview, canPublish, busy, onValidate, onSubmit, onReview, onPublish }: SemanticValidationPanelProps) {
    const errors = issues.filter((issue) => issue.severity === "error");
    return (
        <section className="border-t border-ink/10 bg-white px-6 py-4 lg:px-8">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                    {errors.length ? <CircleAlert className="h-5 w-5 text-oxide" aria-hidden="true" /> : <CheckCircle2 className="h-5 w-5 text-pine" aria-hidden="true" />}
                    <div><p className="text-sm font-semibold text-ink">草稿检查</p><p className="text-xs text-ink/50">{status ? `当前状态：${status}` : "保存后可校验、送审和发布"}{errors.length ? ` · ${errors.length} 个错误` : " · 暂无阻断错误"}</p></div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <button type="button" onClick={onValidate} disabled={busy} className="inline-flex min-h-9 items-center gap-2 border border-ink/15 px-3 text-xs font-semibold text-ink transition hover:bg-paper disabled:cursor-not-allowed disabled:opacity-45"><ShieldCheck className="h-4 w-4" aria-hidden="true" />校验</button>
                    <button type="button" onClick={onSubmit} disabled={busy || !status || status !== "draft" || errors.length > 0} className="inline-flex min-h-9 items-center gap-2 bg-indigo px-3 text-xs font-semibold text-paper transition hover:bg-dai disabled:cursor-not-allowed disabled:opacity-45"><Send className="h-4 w-4" aria-hidden="true" />提交审核</button>
                    {canReview && <><button type="button" onClick={() => onReview("approved")} disabled={busy} className="inline-flex min-h-9 items-center gap-2 bg-pine px-3 text-xs font-semibold text-white disabled:opacity-45"><CheckCircle2 className="h-4 w-4" aria-hidden="true" />通过</button><button type="button" onClick={() => onReview("rejected")} disabled={busy} className="inline-flex min-h-9 items-center gap-2 border border-oxide/30 px-3 text-xs font-semibold text-oxide disabled:opacity-45"><XCircle className="h-4 w-4" aria-hidden="true" />驳回</button></>}
                    {canPublish && <button type="button" onClick={onPublish} disabled={busy} className="inline-flex min-h-9 items-center gap-2 bg-cinnabar px-3 text-xs font-semibold text-white disabled:opacity-45">发布版本</button>}
                </div>
            </div>
            {issues.length > 0 && <div className="mt-3 grid gap-2 lg:grid-cols-2">{issues.map((issue, index) => <div key={`${issue.path}-${index}`} className={`border-l-2 px-3 py-2 text-xs ${issue.severity === "error" ? "border-oxide bg-oxide/5 text-oxide" : "border-cinnabar bg-cinnabar/5 text-ink/70"}`}><span className="font-mono">{issue.path || "model"}</span><span className="mx-2 text-ink/30">·</span>{issue.message}</div>)}</div>}
        </section>
    );
}
