import { ArrowLeft, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
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
import { createDraftSemanticMember, createSemanticModelRequestGate, formatSemanticModelError, mergeSemanticMemberSummaries, resolveSemanticModelSnapshot, semanticCubeOptions, serializeSemanticSnapshot, type SemanticDraft, type SemanticMember, type SemanticMemberSummary, type SemanticMetricAttachment, type SemanticMetricEquivalenceGroup, type SemanticOperation, type SemanticRelease, type SemanticSnapshot, type SemanticValidationIssue, type SemanticCube, type SemanticMemberType } from "../lib/semanticModel";
import { SemanticMemberEditor } from "./SemanticMemberEditor";
import { SemanticMemberList } from "./SemanticMemberList";
import { SemanticReleasePanel } from "./SemanticReleasePanel";
import { SemanticValidationPanel } from "./SemanticValidationPanel";

type SemanticModelPageProps = { onBack: () => void; onDirtyChange?: (dirty: boolean) => void };
type Filters = { memberType: "all" | "measure" | "dimension" | "time_dimension"; query: string };
type CreateMemberType = SemanticMemberType;

const emptySnapshot = resolveSemanticModelSnapshot(undefined);

function asPayload(snapshot: SemanticSnapshot, reason: string): SemanticDraftPayload {
    return serializeSemanticSnapshot(snapshot, reason);
}

function operationIssues(operation: SemanticOperation | null): SemanticValidationIssue[] {
    return operation?.issues ?? [];
}

function defaultCubeName(cubes: SemanticCube[]): string {
    return (
        cubes.find((cube) => cube.public)?.cube_name ??
        cubes.find((cube) => cube.cube_name === "ecommerce")?.cube_name ??
        cubes[0]?.cube_name ??
        ""
    );
}

export function SemanticModelPage({ onBack, onDirtyChange }: SemanticModelPageProps) {
    const [filters, setFilters] = useState<Filters>({ memberType: "all", query: "" });
    const [members, setMembers] = useState<SemanticMemberSummary[]>([]);
    const [snapshot, setSnapshot] = useState<SemanticSnapshot>(emptySnapshot);
    const [activeSnapshot, setActiveSnapshot] = useState<SemanticSnapshot>(emptySnapshot);
    const [draft, setDraft] = useState<SemanticDraft | null>(null);
    const [releases, setReleases] = useState<SemanticRelease[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [createMemberType, setCreateMemberType] = useState<CreateMemberType | null>(null);
    const [createCubeName, setCreateCubeName] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [snapshotUnavailable, setSnapshotUnavailable] = useState(false);
    const [operation, setOperation] = useState<SemanticOperation | null>(null);
    const [busy, setBusy] = useState(false);
    const [dirty, setDirty] = useState(false);
    const requestGateRef = useRef(createSemanticModelRequestGate());

    const load = async () => {
        const generation = requestGateRef.current.start();
        setLoading(true);
        setError(null);
        setSnapshotUnavailable(false);
        try {
            const [memberResponse, releaseResponse] = await Promise.all([listSemanticMembers(filters.memberType, filters.query), listSemanticReleases()]);
            if (!requestGateRef.current.accepts(generation)) return;
            setMembers(memberResponse.items);
            setReleases(releaseResponse.items);
            const active = releaseResponse.items.find((item) => item.active);
            const releaseDetail = active && !active.snapshot
                ? await getSemanticRelease(active.release_version)
                : null;
            const nextSnapshot = resolveSemanticModelSnapshot(active, releaseDetail);
            if (!requestGateRef.current.accepts(generation)) return;
            setSnapshot(nextSnapshot);
            setActiveSnapshot(nextSnapshot);
            setSelectedId((current) => current ?? memberResponse.items[0]?.member_id ?? nextSnapshot.members[0]?.member_id ?? null);
            setDirty(false);
        } catch (loadError) {
            if (requestGateRef.current.accepts(generation)) {
                setSnapshotUnavailable(true);
                setError(formatSemanticModelError(loadError));
            }
        } finally {
            if (requestGateRef.current.accepts(generation)) setLoading(false);
        }
    };

    useEffect(() => { void load(); }, [filters.memberType, filters.query]);
    useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);

    const workingSnapshot = draft?.snapshot ?? snapshot;
    const updateWorkingSnapshot = (update: (current: SemanticSnapshot) => SemanticSnapshot) => {
        setSnapshot((current) => update(current));
        if (draft) setDraft((current) => current ? { ...current, snapshot: update(current.snapshot) } : current);
        setDirty(true);
    };

    const updateMember = (member: SemanticMember) => {
        updateWorkingSnapshot((current) => ({
            ...current,
            release_version: workingSnapshot.release_version,
            members: current.members.map((item) => item.member_id === member.member_id ? member : item),
        }));
    };

    const updateRelations = (groups: SemanticMetricEquivalenceGroup[], attachments: SemanticMetricAttachment[]) => {
        updateWorkingSnapshot((current) => ({
            ...current,
            metric_equivalence_groups: groups,
            metric_attachments: attachments,
        }));
    };

    const requestCreateMember = (memberType: CreateMemberType) => {
        setCreateMemberType(memberType);
        setCreateCubeName(defaultCubeName(semanticCubeOptions(workingSnapshot)));
    };

    const cancelCreateMember = () => {
        setCreateMemberType(null);
        setCreateCubeName("");
    };

    const createMember = (memberType: CreateMemberType, cubeName: string) => {
        if (!cubeName) {
            setError("当前语义模型没有可用 Cube，无法创建成员。");
            return;
        }
        const member = createDraftSemanticMember(workingSnapshot, memberType, cubeName);
        updateWorkingSnapshot((current) => ({ ...current, members: [...current.members, member] }));
        setSelectedId(member.member_id);
        cancelCreateMember();
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
    const directoryMembers = mergeSemanticMemberSummaries(members, currentDraft.members, filters);
    return (
        <div className="relative flex min-h-0 flex-1 flex-col bg-paper">
            <header className="flex min-h-16 shrink-0 items-center justify-between border-b border-ink/10 bg-white px-5 lg:px-7">
                <div className="flex min-w-0 items-center gap-4"><button type="button" onClick={onBack} disabled={busy} title="返回问数工作台" aria-label="返回问数工作台" className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink/60 hover:bg-ink/5 disabled:opacity-40"><ArrowLeft className="h-4 w-4" aria-hidden="true" /></button><div className="min-w-0"><p className="font-serif text-xl font-bold text-ink">指标与维度治理</p><p className="truncate text-xs text-ink/50">维护统一语义成员，发布后供问数链路使用</p></div></div>
                <div className="flex items-center gap-3"><span className="hidden text-xs text-ink/50 lg:inline">生效版本：<span className="font-mono text-ink">{releases.find((item) => item.active)?.release_version ?? "暂无"}</span></span><button type="button" onClick={refresh} disabled={loading || busy} title="刷新治理数据" aria-label="刷新治理数据" className="grid h-10 w-10 place-items-center rounded-full text-ink/60 hover:bg-ink/5 disabled:opacity-40"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" /></button></div>
            </header>
            {error && <div role="alert" className="border-b border-oxide/20 bg-oxide/5 px-6 py-3 text-sm text-oxide">{error}</div>}
            <div className="flex min-h-0 flex-1">
                <SemanticMemberList items={directoryMembers} selectedId={selectedId} filters={filters} loading={loading} disabled={busy || loading || snapshotUnavailable} error={error && !directoryMembers.length ? error : null} onSelect={setSelectedId} onFilterChange={changeFilters} onCreate={requestCreateMember} cubes={workingSnapshot.cubes} />
                <div className="flex min-w-0 flex-1 flex-col">
                    <SemanticMemberEditor
                        member={currentDraft.members.find((member) => member.member_id === selectedId) ?? null}
                        members={currentDraft.members}
                        metricEquivalenceGroups={currentDraft.metric_equivalence_groups ?? []}
                        metricAttachments={currentDraft.metric_attachments ?? []}
                        disabled={busy || loading || snapshotUnavailable}
                        onChange={updateMember}
                        onRelationsChange={updateRelations}
                        onSave={() => void save()}
                    />
                    <SemanticValidationPanel issues={operationIssues(operation)} status={draft?.status ?? null} canReview={draft?.status === "pending_review"} canPublish={draft?.status === "validated"} busy={busy} onValidate={() => { const current = requireDraft(); if (current) void perform(() => validateSemanticDraft(current.draft_id), ""); }} onSubmit={() => { const current = requireDraft(); if (current) void perform(() => submitSemanticDraft(current.draft_id, { reason: "提交语义模型审核" }), ""); }} onReview={(decision) => { const current = requireDraft(); if (current) void perform(() => reviewSemanticDraft(current.draft_id, { decision, reason: decision === "approved" ? "审核通过" : "审核驳回" }), ""); }} onPublish={() => { const current = requireDraft(); if (current) void perform(() => publishSemanticDraft(current.draft_id, { reason: "发布语义模型版本" }), ""); }} />
                </div>
                <SemanticReleasePanel releases={releases} activeVersion={releases.find((item) => item.active)?.release_version ?? null} activeSnapshot={activeSnapshot} disabled={busy} onRollback={handleRollback} />
            </div>
            {createMemberType && (
                <div className="absolute inset-0 z-20 flex items-start justify-center bg-ink/10 p-10" role="presentation">
                    <div
                        className="w-full max-w-xl border border-ink/15 bg-white p-6 shadow-line"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="create-member-title"
                    >
                        <div className="flex items-start justify-between gap-6">
                            <div>
                                <p id="create-member-title" className="font-serif text-lg font-bold text-ink">
                                    新增{createMemberType === "measure" ? "指标" : createMemberType === "dimension" ? "维度" : "时间维度"}
                                </p>
                                <p className="mt-1 text-sm text-ink/55">请选择该成员所属的 Cube，创建后不可在本批次迁移。</p>
                            </div>
                            <span className="font-mono text-xs text-ink/45">CREATE</span>
                        </div>
                        {semanticCubeOptions(workingSnapshot).length > 0 ? (
                            <label className="mt-6 block text-sm font-semibold text-ink">
                                <span className="mb-2 block">所属 Cube</span>
                                <select
                                    value={createCubeName}
                                    onChange={(event) => setCreateCubeName(event.target.value)}
                                    disabled={busy || loading}
                                    className="h-11 w-full border border-ink/15 bg-paper px-3 text-sm font-normal text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                    {semanticCubeOptions(workingSnapshot).map((cube) => (
                                        <option key={cube.cube_name} value={cube.cube_name}>
                                            {cube.cube_name}{cube.title ? ` · ${cube.title}` : ""}
                                        </option>
                                    ))}
                                </select>
                            </label>
                        ) : (
                            <p role="alert" className="mt-6 border-l-2 border-oxide bg-oxide/5 p-3 text-sm text-oxide">
                                当前语义模型没有可用 Cube，无法创建成员。
                            </p>
                        )}
                        <div className="mt-7 flex justify-end gap-3">
                            <button type="button" onClick={cancelCreateMember} className="min-h-10 border border-ink/15 px-4 text-sm font-semibold text-ink/65 transition hover:bg-paper focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40">
                                取消
                            </button>
                            <button
                                type="button"
                                onClick={() => createMember(createMemberType, createCubeName)}
                                disabled={!createCubeName || semanticCubeOptions(workingSnapshot).length === 0 || busy || loading || snapshotUnavailable}
                                className="min-h-10 bg-dai px-4 text-sm font-semibold text-paper transition hover:bg-dai/90 disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40"
                            >
                                创建成员
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
