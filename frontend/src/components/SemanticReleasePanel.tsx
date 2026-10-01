import { History, RotateCcw } from "lucide-react";
import type { SemanticRelease } from "../lib/semanticModel";

type SemanticReleasePanelProps = {
    releases: SemanticRelease[];
    activeVersion: string | null;
    disabled: boolean;
    onRollback: (release: SemanticRelease) => void;
};

export function SemanticReleasePanel({ releases, activeVersion, disabled, onRollback }: SemanticReleasePanelProps) {
    return (
        <aside className="w-[19rem] shrink-0 border-l border-ink/10 bg-paper p-5">
            <div className="flex items-center gap-2"><History className="h-4 w-4 text-indigo" aria-hidden="true" /><h2 className="font-serif text-base font-bold text-ink">发布记录</h2></div>
            <p className="mt-2 text-xs leading-5 text-ink/50">当前生效版本会同时供问数链路和 Cube 元数据读取。</p>
            <div className="mt-5 space-y-2">{releases.length === 0 && <p className="text-sm text-ink/45">暂无发布版本。</p>}{releases.map((release) => { const active = release.active || release.release_version === activeVersion; return <div key={release.release_version} className={`border p-3 ${active ? "border-pine/40 bg-pine/5" : "border-ink/10 bg-white"}`}><div className="flex items-center justify-between gap-2"><span className="font-mono text-xs font-semibold text-ink">{release.release_version}</span>{active && <span className="text-[11px] font-semibold text-pine">生效中</span>}</div><p className="mt-2 text-xs text-ink/55">状态：{release.status}</p>{release.error_code && <p className="mt-1 text-xs text-oxide">{release.error_code}</p>}{!active && <button type="button" onClick={() => onRollback(release)} disabled={disabled} className="mt-3 inline-flex min-h-8 items-center gap-2 text-xs font-semibold text-oxide hover:text-cinnabar disabled:opacity-45"><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />请求回滚</button>}</div>; })}</div>
        </aside>
    );
}
