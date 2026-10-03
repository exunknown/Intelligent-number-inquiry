import { CheckCircle2, CircleAlert } from "lucide-react";
import type { SemanticChangeSummary, SemanticValidationIssue } from "../lib/semanticModel";

type SemanticValidationPanelProps = {
    issues: SemanticValidationIssue[];
    status: string | null;
    changeSummary?: SemanticChangeSummary;
};

export function SemanticValidationPanel({ issues, status, changeSummary }: SemanticValidationPanelProps) {
    const errors = issues.filter((issue) => issue.severity === "error");
    const addedMeasures = changeSummary?.added.filter((member) => member.member_type === "measure") ?? [];
    const addedDimensions = changeSummary?.added.filter((member) => member.member_type === "dimension") ?? [];
    const addedTimeDimensions = changeSummary?.added.filter((member) => member.member_type === "time_dimension") ?? [];
    return (
        <section className="border-t border-ink/10 bg-white px-6 py-4 lg:px-8">
            {changeSummary && <section className="mb-4 border-l-2 border-cinnabar bg-cinnabar/5 px-4 py-3" aria-labelledby="semantic-change-summary-title">
                <h2 id="semantic-change-summary-title" className="text-xs font-semibold text-ink">发布前变更摘要</h2>
                {!changeSummary.has_changes ? <p className="mt-2 text-xs text-ink/55">暂无成员或关系变更</p> : <div className="mt-2 grid gap-2 text-xs text-ink/70 lg:grid-cols-2">
                    {addedMeasures.length > 0 && <div><p className="font-semibold text-ink">新增指标</p><ul className="mt-1 space-y-1">{addedMeasures.map((item) => <li key={item.member_id}>{item.title || item.member_name} <span className="font-mono text-ink/45">({item.member_id})</span></li>)}</ul></div>}
                    {addedDimensions.length > 0 && <div><p className="font-semibold text-ink">新增维度</p><ul className="mt-1 space-y-1">{addedDimensions.map((item) => <li key={item.member_id}>{item.title || item.member_name} <span className="font-mono text-ink/45">({item.member_id})</span></li>)}</ul></div>}
                    {addedTimeDimensions.length > 0 && <div><p className="font-semibold text-ink">新增时间维度</p><ul className="mt-1 space-y-1">{addedTimeDimensions.map((item) => <li key={item.member_id}>{item.title || item.member_name} <span className="font-mono text-ink/45">({item.member_id})</span></li>)}</ul></div>}
                    {changeSummary.changed.length > 0 && <div><p className="font-semibold text-ink">修改指标口径</p><ul className="mt-1 space-y-1">{changeSummary.changed.map((item) => <li key={item.member_id}>{item.title || item.member_name} <span className="font-mono text-ink/45">({item.member_id})</span></li>)}</ul></div>}
                    {changeSummary.removed.length > 0 && <div><p className="font-semibold text-ink">删除或下线成员</p><ul className="mt-1 space-y-1">{changeSummary.removed.map((item) => <li key={item.member_id}>{item.title || item.member_name} <span className="font-mono text-ink/45">({item.member_id})</span></li>)}</ul></div>}
                    {changeSummary.equivalence_changed && <p>等效指标关系：已变更</p>}
                    {changeSummary.attachments_changed && <p>附带指标关系：已变更</p>}
                </div>}
            </section>}
            <div className="flex items-center gap-3">
                <div className="flex items-center gap-3">
                    {errors.length ? <CircleAlert className="h-5 w-5 text-oxide" aria-hidden="true" /> : <CheckCircle2 className="h-5 w-5 text-pine" aria-hidden="true" />}
                    <div><p className="text-sm font-semibold text-ink">草稿检查</p><p className="text-xs text-ink/50">{status ? `当前状态：${status}` : "保存后可校验、送审和发布"}{errors.length ? ` · ${errors.length} 个错误` : " · 暂无阻断错误"}</p></div>
                </div>
            </div>
            {issues.length > 0 && <div className="mt-3 grid gap-2 lg:grid-cols-2">{issues.map((issue, index) => <div key={`${issue.path}-${index}`} className={`border-l-2 px-3 py-2 text-xs ${issue.severity === "error" ? "border-oxide bg-oxide/5 text-oxide" : "border-cinnabar bg-cinnabar/5 text-ink/70"}`}><span className="font-mono">{issue.code}</span><span className="mx-2 text-ink/30">·</span><span className="font-mono">{issue.path || "model"}</span><span className="mx-2 text-ink/30">·</span>{issue.message}</div>)}</div>}
        </section>
    );
}
