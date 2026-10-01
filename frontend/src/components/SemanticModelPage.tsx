import { ArrowLeft, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
    createSemanticDraft,
    getSemanticDraft,
    getSemanticRelease,
    listSemanticMembers,
    listSemanticReleases,
    publishSemanticDraft,
    reviewSemanticDraft,
    rollbackSemanticRelease,
    submitSemanticDraft,
    updateSemanticDraft,
    validateSemanticDraft,
    type SemanticDraftPayload,
} from "../lib/agentApi";
import { createSemanticModelRequestGate, formatSemanticModelError, type SemanticDraft, type SemanticMember, type SemanticMemberSummary, type SemanticOperation, type SemanticRelease, type SemanticSnapshot, type SemanticValidationIssue } from "../lib/semanticModel";
import { SemanticMemberEditor } from "./SemanticMemberEditor";
import { SemanticMemberList } from "./SemanticMemberList";
import { SemanticReleasePanel } from "./SemanticReleasePanel";
import { SemanticValidationPanel } from "./SemanticValidationPanel";

type SemanticModelPageProps = { onBack: () => void; onDirtyChange?: (dirty: boolean) => void };
type Filters = { memberType: "all" | "measure" | "dimension" | "time_dimension"; query: string };

const emptySnapshot: SemanticSnapshot = { release_version: "draft", cubes: [], joins: [], members: [] };

function asPayload(snapshot: SemanticSnapshot, reason: string): SemanticDraftPayload {
    return {
        release_version: snapshot.release_version,
        cubes: snapshot.cubes,
        joins: snapshot.joins,
        members: snapshot.members,
        metric_equivalence_groups: snapshot.metric_equivalence_groups ?? [],
        metric_attachments: snapshot.metric_attachments ?? [],
        reason,
    };
}

function operationIssues(operation: SemanticOperation | null): SemanticValidationIssue[] {
    return operation?.issues ?? [];
}

export function SemanticModelPage({ onBack, onDirtyChange }: SemanticModelPageProps) {
    const [filters, setFilters] = useState<Filters>({ memberType: "all", query: "" });
    const [members, setMembers] = useState<SemanticMemberSummary[]>([]);
    const [snapshot, setSnapshot] = useState<SemanticSnapshot>(emptySnapshot);
    const [draft, setDraft] = useState<SemanticDraft | null>(null);
    const [releases, setReleases] = useState<SemanticRelease[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [operation, setOperation] = useState<SemanticOperation | null>(null);
    const [busy, setBusy] = useState(false);
    const [dirty, setDirty] = useState(false);
    const requestGateRef = useRef(createSemanticModelRequestGate());

    const selectedMember = useMemo(() => snapshot.members.find((member) => member.member_id === selectedId) ?? null, [selectedId, snapshot.members]);

    const load = async () => {
        const generation = requestGateRef.current.start();
        setLoading(true);
        setError(null);
        try {
            const [memberResponse, releaseResponse] = await Promise.all([listSemanticMembers(filters.memberType, filters.query), listSemanticReleases()]);
            if (!requestGateRef.current.accepts(generation)) return;
            setMembers(memberResponse.items);
            setReleases(releaseResponse.items);
            const active = releaseResponse.items.find((item) => item.active);
            let nextSnapshot = active?.snapshot ? active.snapshot : emptySnapshot;
            if (active && !active.snapshot) nextSnapshot = (await getSemanticRelease(active.release_version)).snapshot ?? emptySnapshot;
            if (!requestGateRef.current.accepts(generation)) return;
            setSnapshot(nextSnapshot);
            setSelectedId((current) => current && memberResponse.items.some((item) => item.member_id === current) ? current : memberResponse.items[0]?.member_id ?? nextSnapshot.members[0]?.member_id ?? null);
            setDirty(false);
        } catch (loadError) {
            if (requestGateRef.current.accepts(generation)) setError(formatSemanticModelError(loadError));
        } finally {
            if (requestGateRef.current.accepts(generation)) setLoading(false);
        }
    };

    useEffect(() => { void load(); }, [filters.memberType, filters.query]);
    useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);

    const workingSnapshot = draft?.snapshot ?? snapshot;
    const updateMember = (member: SemanticMember) => {
        setSnapshot((current) => ({ ...current, release_version: workingSnapshot.release_version, members: current.members.map((item) => item.member_id === member.member_id ? member : item) }));
        if (draft) setDraft((current) => current ? { ...current, snapshot: { ...current.snapshot, members: current.snapshot.members.map((item) => item.member_id === member.member_id ? member : item) } } : current);
        setDirty(true);
    };

    const refreshDraft = async (draftId: string) => {
        const response = await getSemanticDraft(draftId);
        setDraft(response);
        setSnapshot(response.snapshot);
        setDirty(false);
    };

    const perform = async (action: () => Promise<SemanticOperation>, success: string) => {
        setBusy(true);
        setError(null);
        try {
            const result = await action();
            setOperation(result);
            if (!result.draft_id) setDraft(null);
            if (result.draft_id) await refreshDraft(result.draft_id);
            await load();
            if (result.status === "failed") setError(formatSemanticModelError({ status: 422, message: result.error_code ?? "操作未完成" }));
            else if (success) setError(null);
        } catch (actionError) {
            setError(formatSemanticModelError(actionError));
        } finally {
            setBusy(false);
        }
    };

    const save = async () => {
        const reason = "更新指标和维度治理草稿";
        const payload = asPayload(workingSnapshot, reason);
        await perform(async () => {
            if (draft) return updateSemanticDraft(draft.draft_id, payload);
            return createSemanticDraft(payload);
        }, "");
    };

    const requireDraft = () => {
        if (!draft) {
            setError("请先保存草稿，再执行校验或流转操作。");
            return null;
        }
        return draft;
    };

    const handleRollback = (release: SemanticRelease) => {
        const reason = window.prompt(`请输入回滚 ${release.release_version} 的原因`);
        if (!reason?.trim()) return;
        void perform(() => rollbackSemanticRelease(release.release_version, { reason: reason.trim() }), "");
    };

    const changeFilters = (nextFilters: Filters) => {
        if (dirty && !window.confirm("当前指标治理草稿尚未保存，切换筛选会丢失修改，确定继续吗？")) return;
        setDraft(null);
        setDirty(false);
        setFilters(nextFilters);
    };

    const refresh = () => {
        if (dirty && !window.confirm("当前指标治理草稿尚未保存，刷新会丢失修改，确定继续吗？")) return;
        setDraft(null);
        setDirty(false);
        void load();
    };

    const currentDraft = draft?.snapshot ?? snapshot;
    return (
        <div className="flex min-h-0 flex-1 flex-col bg-paper">
            <header className="flex min-h-16 shrink-0 items-center justify-between border-b border-ink/10 bg-white px-5 lg:px-7">
                <div className="flex min-w-0 items-center gap-4"><button type="button" onClick={onBack} disabled={busy} title="返回问数工作台" aria-label="返回问数工作台" className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink/60 hover:bg-ink/5 disabled:opacity-40"><ArrowLeft className="h-4 w-4" aria-hidden="true" /></button><div className="min-w-0"><p className="font-serif text-xl font-bold text-ink">指标与维度治理</p><p className="truncate text-xs text-ink/50">维护统一语义成员，发布后供问数链路使用</p></div></div>
                <div className="flex items-center gap-3"><span className="hidden text-xs text-ink/50 lg:inline">生效版本：<span className="font-mono text-ink">{releases.find((item) => item.active)?.release_version ?? "暂无"}</span></span><button type="button" onClick={refresh} disabled={loading || busy} title="刷新治理数据" aria-label="刷新治理数据" className="grid h-10 w-10 place-items-center rounded-full text-ink/60 hover:bg-ink/5 disabled:opacity-40"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" /></button></div>
            </header>
            {error && <div role="alert" className="border-b border-oxide/20 bg-oxide/5 px-6 py-3 text-sm text-oxide">{error}</div>}
            <div className="flex min-h-0 flex-1">
                <SemanticMemberList items={members} selectedId={selectedId} filters={filters} loading={loading} error={error && !members.length ? error : null} onSelect={setSelectedId} onFilterChange={changeFilters} />
                <div className="flex min-w-0 flex-1 flex-col">
                    <SemanticMemberEditor member={currentDraft.members.find((member) => member.member_id === selectedId) ?? null} disabled={busy || loading} onChange={updateMember} onSave={() => void save()} />
                    <SemanticValidationPanel issues={operationIssues(operation)} status={draft?.status ?? null} canReview={draft?.status === "pending_review"} canPublish={draft?.status === "validated"} busy={busy} onValidate={() => { const current = requireDraft(); if (current) void perform(() => validateSemanticDraft(current.draft_id), ""); }} onSubmit={() => { const current = requireDraft(); if (current) void perform(() => submitSemanticDraft(current.draft_id, { reason: "提交语义模型审核" }), ""); }} onReview={(decision) => { const current = requireDraft(); if (current) void perform(() => reviewSemanticDraft(current.draft_id, { decision, reason: decision === "approved" ? "审核通过" : "审核驳回" }), ""); }} onPublish={() => { const current = requireDraft(); if (current) void perform(() => publishSemanticDraft(current.draft_id, { reason: "发布语义模型版本" }), ""); }} />
                </div>
                <SemanticReleasePanel releases={releases} activeVersion={releases.find((item) => item.active)?.release_version ?? null} disabled={busy} onRollback={handleRollback} />
            </div>
        </div>
    );
}
