import { History, X } from "lucide-react";
import type { SemanticRelease, SemanticSnapshot } from "../lib/semanticModel";

type SemanticReleasePanelProps = {
    releases: SemanticRelease[];
    activeVersion: string | null;
    activeSnapshot: SemanticSnapshot | null;
    onClose: () => void;
};

export function SemanticReleasePanel({
    releases,
    activeVersion,
    activeSnapshot,
    onClose,
}: SemanticReleasePanelProps) {
    const snapshotReady = activeSnapshot !== null && (!activeVersion || activeSnapshot.release_version === activeVersion);
    const groups = activeSnapshot?.metric_equivalence_groups ?? [];
    const attachments = activeSnapshot?.metric_attachments ?? [];
    return (
        <section
            className="w-full max-w-2xl overflow-hidden rounded-2xl border border-ink/15 bg-paper shadow-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="semantic-release-dialog-title"
        >
            <header className="flex items-start justify-between gap-6 border-b border-ink/10 bg-white px-6 py-5">
                <div className="flex items-start gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-indigo/10 text-indigo">
                        <History className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div>
                        <h2 id="semantic-release-dialog-title" className="font-serif text-lg font-bold text-ink">发布记录</h2>
                        <p className="mt-1 text-xs leading-5 text-ink/50">查看语义模型历史版本与当前生效状态。</p>
                    </div>
                </div>
                <button
                    type="button"
                    onClick={onClose}
                    title="关闭发布记录"
                    aria-label="关闭发布记录"
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-ink/50 transition hover:bg-ink/5 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                >
                    <X className="h-4 w-4" aria-hidden="true" />
                </button>
            </header>
            <div className="max-h-[min(32rem,calc(100vh-13rem))] overflow-y-auto px-6 py-5">
                <div className="rounded-xl border border-pine/30 bg-pine/5 p-4">
                    <div className="flex items-center justify-between gap-3">
                        <p className="text-xs font-semibold text-ink/65">当前生效版本</p>
                        {snapshotReady && <span className="rounded-full bg-pine/10 px-2 py-1 text-[11px] font-semibold text-pine">生效中</span>}
                    </div>
                    {snapshotReady ? (
                        <>
                            <p className="mt-3 font-mono text-sm font-semibold text-ink">{activeSnapshot.release_version}</p>
                            <p className="mt-2 text-xs leading-5 text-ink/55">当前版本会同时供问数链路和 Cube 元数据读取。</p>
                        </>
                    ) : (
                        <p className="mt-3 text-xs leading-5 text-ink/45">当前版本关系预览暂不可用。</p>
                    )}
                </div>
                <div className="mt-6 border-t border-ink/10 pt-5">
                    <div className="flex items-center justify-between gap-3">
                        <h3 className="text-sm font-semibold text-ink">当前版本关系预览</h3>
                        {snapshotReady && <span className="font-mono text-[11px] text-ink/45">{activeSnapshot.release_version}</span>}
                    </div>
                    {snapshotReady ? (
                        <>
                            <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-ink/60">
                                <span>等效组 <strong className="font-mono text-ink">{groups.length}</strong></span>
                                <span>附带关系 <strong className="font-mono text-ink">{attachments.length}</strong></span>
                            </div>
                            {groups.slice(0, 3).map((group) => <div key={group.group_id} className="mt-2 truncate text-xs text-ink/55" title={group.group_name}>{group.group_name || group.group_id} · {group.members.length} 个成员</div>)}
                            {groups.length > 3 && <p className="mt-1 text-[11px] text-ink/40">另有 {groups.length - 3} 个等效组</p>}
                        </>
                    ) : (
                        <p className="mt-3 text-xs leading-5 text-ink/45">快照未准备好，暂不展示关系统计。</p>
                    )}
                </div>
                <div className="mt-6 border-t border-ink/10 pt-5">
                    <div className="flex items-center justify-between gap-3">
                        <h3 className="text-sm font-semibold text-ink">历史版本</h3>
                        <span className="text-xs text-ink/45">共 {releases.length} 个版本</span>
                    </div>
                    <div className="mt-3 space-y-2">
                        {releases.length === 0 && <p className="text-sm text-ink/45">暂无发布版本。</p>}
                        {releases.map((release) => {
                            const active = release.active || release.release_version === activeVersion;
                            return (
                                <div key={release.release_version} className={`rounded-lg border p-3 ${active ? "border-pine/35 bg-pine/5" : "border-ink/10 bg-white"}`}>
                                    <div className="flex items-center justify-between gap-3">
                                        <span className="font-mono text-xs font-semibold text-ink">{release.release_version}</span>
                                        {active && <span className="rounded-full bg-pine/10 px-2 py-1 text-[11px] font-semibold text-pine">生效中</span>}
                                    </div>
                                    <p className="mt-2 text-xs text-ink/55">状态：{release.status}</p>
                                    {release.error_code && <p className="mt-1 text-xs text-oxide">{release.error_code}</p>}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
            <footer className="flex justify-end border-t border-ink/10 bg-white px-6 py-4">
                <button
                    type="button"
                    onClick={onClose}
                    className="min-h-9 rounded-lg bg-cinnabar px-4 text-xs font-semibold text-white transition hover:bg-dai focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                >
                    关闭
                </button>
            </footer>
        </section>
    );
}
