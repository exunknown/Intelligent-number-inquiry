import { History, RotateCcw } from "lucide-react";
import type { SemanticRelease, SemanticSnapshot } from "../lib/semanticModel";

type SemanticReleasePanelProps = {
    releases: SemanticRelease[];
    activeVersion: string | null;
    disabled: boolean;
    dirty: boolean;
    onRollback: (release: SemanticRelease) => void;
    activeSnapshot: SemanticSnapshot | null;
};

export function SemanticReleasePanel({ releases, activeVersion, disabled, dirty, onRollback, activeSnapshot }: SemanticReleasePanelProps) {
    const snapshotReady = activeSnapshot !== null && (!activeVersion || activeSnapshot.release_version === activeVersion);
    const groups = activeSnapshot?.metric_equivalence_groups ?? [];
    const attachments = activeSnapshot?.metric_attachments ?? [];
    return (
        <aside className="w-[19rem] shrink-0 border-l border-ink/10 bg-paper p-5">
            <div className="flex items-center gap-2"><History className="h-4 w-4 text-indigo" aria-hidden="true" /><h2 className="font-serif text-base font-bold text-ink">发布记录</h2></div>
            <p className="mt-2 text-xs leading-5 text-ink/50">当前生效版本会同时供问数链路和 Cube 元数据读取。</p>
            <div className="mt-4 border-y border-ink/10 py-3">
                {snapshotReady ? <>
                    <div className="flex items-center justify-between gap-2"><p className="text-xs font-semibold text-ink/65">当前版本关系预览</p><span className="font-mono text-[11px] text-ink/45">{activeSnapshot?.release_version}</span></div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-ink/60"><span>等效组 <strong className="font-mono text-ink">{groups.length}</strong></span><span>附带关系 <strong className="font-mono text-ink">{attachments.length}</strong></span></div>
                    {groups.slice(0, 3).map((group) => <div key={group.group_id} className="mt-2 truncate text-xs text-ink/55" title={group.group_name}>{group.group_name || group.group_id} · {group.members.length} 个成员</div>)}
                    {groups.length > 3 && <p className="mt-1 text-[11px] text-ink/40">另有 {groups.length - 3} 个等效组</p>}
                </> : <p className="text-xs leading-5 text-ink/45">当前版本关系预览暂不可用。</p>}
            </div>
            <div className="mt-5 space-y-2">{releases.length === 0 && <p className="text-sm text-ink/45">暂无发布版本。</p>}{releases.map((release) => { const active = release.active || release.release_version === activeVersion; return <div key={release.release_version} className={`border p-3 ${active ? "border-pine/40 bg-pine/5" : "border-ink/10 bg-white"}`}><div className="flex items-center justify-between gap-2"><span className="font-mono text-xs font-semibold text-ink">{release.release_version}</span>{active && <span className="text-[11px] font-semibold text-pine">生效中</span>}</div><p className="mt-2 text-xs text-ink/55">状态：{release.status}</p>{release.error_code && <p className="mt-1 text-xs text-oxide">{release.error_code}</p>}{!active && <button type="button" onClick={() => onRollback(release)} disabled={disabled || dirty || !snapshotReady} className="mt-3 inline-flex min-h-8 items-center gap-2 text-xs font-semibold text-oxide hover:text-cinnabar disabled:opacity-45"><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />请求回滚</button>}</div>; })}</div>
        </aside>
    );
}
