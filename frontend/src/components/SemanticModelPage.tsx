import { ArrowLeft, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
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
import { buildSemanticChangeSummary, buildSemanticMemberId, cloneSemanticSnapshot, copySemanticMeasure, copySemanticMember, createDraftSemanticMember, createSemanticModelRequestGate, formatSemanticModelError, renamePendingSemanticMemberId, renameSemanticMemberReferences, resolveSemanticModelSnapshot, semanticCubeOptions, semanticDependencyCandidates, semanticDirectoryLoadAllowed, semanticMemberTypesForBuildTab, serializeSemanticSnapshot, validateNewSemanticMemberFields, validateSemanticMemberName, type SemanticBuildTab, type SemanticDraft, type SemanticMember, type SemanticMemberSummary, type SemanticMetricAttachment, type SemanticMetricEquivalenceGroup, type SemanticOperation, type SemanticRelease, type SemanticSnapshot, type SemanticValidationIssue, type SemanticCube, type SemanticMemberType } from "../lib/semanticModel";
import { nextFocusableIndex } from "../lib/userManagement";
import { AgentManagementTabs } from "./AgentManagementTabs";
import { DimensionBuildTable } from "./DimensionBuildTable";
import { MetricBuildTable } from "./MetricBuildTable";
import { SemanticBuildToolbar } from "./SemanticBuildToolbar";
import { SemanticMemberEditDialog } from "./SemanticMemberEditDialog";
import { SemanticReleasePanel } from "./SemanticReleasePanel";
import { SemanticValidationPanel } from "./SemanticValidationPanel";
import { SemanticVersionActionBar } from "./SemanticVersionActionBar";

type SemanticModelPageProps = { onBack: () => void; onDirtyChange?: (dirty: boolean) => void };
type Filters = { memberType: "all" | "measure" | "dimension" | "time_dimension"; query: string };
type CreateMemberType = SemanticMemberType;
type MemberDialogState = {
    mode: "create" | "edit" | "copy";
    member: SemanticMember;
    originalMember: SemanticMember;
    metricEquivalenceGroups: SemanticMetricEquivalenceGroup[];
    metricAttachments: SemanticMetricAttachment[];
    trigger: HTMLButtonElement | null;
} | null;

const emptySnapshot = resolveSemanticModelSnapshot(undefined);
const CREATE_DIALOG_FOCUSABLE_SELECTOR = [
    "button:not([disabled])",
    "[href]",
    "input:not([disabled])",
    "select:not([disabled])",
    "textarea:not([disabled])",
    "[tabindex]:not([tabindex=\"-1\"])",
].join(",");

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
    const [activeTab, setActiveTab] = useState<SemanticBuildTab>("metrics");
    const [directoryQuery, setDirectoryQuery] = useState("");
    const [members, setMembers] = useState<SemanticMemberSummary[]>([]);
    const [snapshot, setSnapshot] = useState<SemanticSnapshot>(emptySnapshot);
    const [activeSnapshot, setActiveSnapshot] = useState<SemanticSnapshot>(emptySnapshot);
    const [draft, setDraft] = useState<SemanticDraft | null>(null);
    const [releases, setReleases] = useState<SemanticRelease[]>([]);
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [pendingNewMemberIds, setPendingNewMemberIds] = useState<string[]>([]);
    const [replacedMemberIds, setReplacedMemberIds] = useState<string[]>([]);
    const [createMemberType, setCreateMemberType] = useState<CreateMemberType | null>(null);
    const [createCubeName, setCreateCubeName] = useState("");
    const [memberDialog, setMemberDialog] = useState<MemberDialogState>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [snapshotUnavailable, setSnapshotUnavailable] = useState(false);
    const [operation, setOperation] = useState<SemanticOperation | null>(null);
    const [busy, setBusy] = useState(false);
    const [dirty, setDirty] = useState(false);
    const [publishBlocked, setPublishBlocked] = useState(false);
    const requestGateRef = useRef(createSemanticModelRequestGate());
    const localEditGenerationRef = useRef(0);
    const createDialogRef = useRef<HTMLDivElement | null>(null);
    const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
    const createTriggerRef = useRef<HTMLButtonElement | null>(null);

    const load = async () => {
        const generation = requestGateRef.current.start();
        const editGeneration = localEditGenerationRef.current;
        const acceptsLocalEdit = () => localEditGenerationRef.current === editGeneration;
        setLoading(true);
        setError(null);
        setSnapshotUnavailable(true);
        try {
            const [memberResponse, releaseResponse] = await Promise.all([listSemanticMembers(filters.memberType, directoryQuery), listSemanticReleases()]);
            if (!requestGateRef.current.accepts(generation)) return;
            setMembers(memberResponse.items);
            if (!acceptsLocalEdit()) {
                setSnapshotUnavailable(false);
                return;
            }
            setReleases(releaseResponse.items);
            const active = releaseResponse.items.find((item) => item.active);
            const releaseDetail = active && !active.snapshot
                ? await getSemanticRelease(active.release_version)
                : null;
            const nextSnapshot = resolveSemanticModelSnapshot(active, releaseDetail);
            if (!requestGateRef.current.accepts(generation)) return;
            if (!acceptsLocalEdit()) {
                setSnapshotUnavailable(false);
                return;
            }
            setSnapshot(nextSnapshot);
            setActiveSnapshot(nextSnapshot);
            setSnapshotUnavailable(false);
            setSelectedId((current) => current ?? memberResponse.items[0]?.member_id ?? nextSnapshot.members[0]?.member_id ?? null);
            setDirty(false);
        } catch (loadError) {
            if (requestGateRef.current.accepts(generation) && acceptsLocalEdit()) {
                setSnapshotUnavailable(true);
                setError(formatSemanticModelError(loadError));
            }
        } finally {
            if (requestGateRef.current.accepts(generation) && acceptsLocalEdit()) setLoading(false);
        }
    };

    useEffect(() => {
        const timer = window.setTimeout(() => {
            setDirectoryQuery(filters.query);
        }, 280);
        return () => window.clearTimeout(timer);
    }, [filters.query]);
    useEffect(() => { if (semanticDirectoryLoadAllowed(dirty)) void load(); }, [filters.memberType, directoryQuery, dirty]);
    useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);

    const workingSnapshot = draft?.snapshot ?? snapshot;
    const beginLocalEdit = () => {
        setLoading(false);
        localEditGenerationRef.current += 1;
    };
    const updateWorkingSnapshot = (update: (current: SemanticSnapshot) => SemanticSnapshot) => {
        beginLocalEdit();
        setSnapshot((current) => update(current));
        if (draft) setDraft((current) => current ? { ...current, snapshot: update(current.snapshot) } : current);
        setDirty(true);
    };

    const openMemberDialog = (
        mode: Exclude<NonNullable<MemberDialogState>["mode"], "copy">,
        member: SemanticMember,
        trigger: HTMLButtonElement | null,
    ) => {
        const memberCopy = structuredClone(member);
        setError(null);
        setMemberDialog({
            mode,
            member: memberCopy,
            originalMember: structuredClone(member),
            metricEquivalenceGroups: structuredClone(
                workingSnapshot.metric_equivalence_groups ?? [],
            ),
            metricAttachments: structuredClone(workingSnapshot.metric_attachments ?? []),
            trigger,
        });
    };

    const openEditMember = (memberId: string, trigger: HTMLButtonElement) => {
        const member = workingSnapshot.members.find((item) => item.member_id === memberId);
        if (member) openMemberDialog("edit", member, trigger);
    };

    const openCopyMember = (memberId: string, trigger: HTMLButtonElement) => {
        const sourceMember = workingSnapshot.members.find((item) => item.member_id === memberId);
        if (!sourceMember) return;
        try {
            if (sourceMember.member_type === "measure") {
                const preparedCopy = copySemanticMeasure(
                    cloneSemanticSnapshot(workingSnapshot),
                    memberId,
                );
                const copiedMember = preparedCopy.snapshot.members.find(
                    (item) => item.member_id === preparedCopy.copiedMemberId,
                );
                if (!copiedMember) return;
                setError(null);
                setMemberDialog({
                    mode: "copy",
                    member: copiedMember,
                    originalMember: structuredClone(sourceMember),
                    metricEquivalenceGroups: preparedCopy.snapshot.metric_equivalence_groups ?? [],
                    metricAttachments: preparedCopy.snapshot.metric_attachments ?? [],
                    trigger,
                });
                return;
            }
            const copiedMember = copySemanticMember(workingSnapshot, memberId);
            setError(null);
            setMemberDialog({
                mode: "copy",
                member: copiedMember,
                originalMember: structuredClone(sourceMember),
                metricEquivalenceGroups: structuredClone(
                    workingSnapshot.metric_equivalence_groups ?? [],
                ),
                metricAttachments: structuredClone(workingSnapshot.metric_attachments ?? []),
                trigger,
            });
        } catch (copyError) {
            setError(formatSemanticModelError(copyError));
        }
    };

    const closeMemberDialog = () => {
        setMemberDialog(null);
        setError(null);
        requestAnimationFrame(() => {
            if (memberDialog?.trigger?.isConnected) {
                memberDialog.trigger.focus();
                return;
            }
            const fallbackFocusTarget =
                document.getElementById("semantic-model-refresh") ??
                document.querySelector<HTMLElement>("#semantic-model-page [role='tab']");
            fallbackFocusTarget?.focus();
        });
    };

    const changeMemberName = (memberName: string) => {
        setMemberDialog((current) => {
            if (!current || memberName === current.member.member_name) return current;
            const validationError = validateSemanticMemberName(
                workingSnapshot,
                current.member,
                memberName,
                current.mode === "edit"
                    ? current.originalMember.member_id
                    : current.member.member_id,
            );
            if (validationError) {
                setError(validationError);
                return {
                    ...current,
                    member: { ...current.member, member_name: memberName },
                };
            }
            const nextMember = {
                ...current.member,
                member_name: memberName,
                member_id: buildSemanticMemberId({
                    ...current.member,
                    member_name: memberName,
                }),
            };
            const renamedDialogSnapshot = renameSemanticMemberReferences(
                {
                    ...workingSnapshot,
                    members: [current.member],
                    metric_equivalence_groups: current.metricEquivalenceGroups,
                    metric_attachments: current.metricAttachments,
                },
                current.member,
                nextMember,
            );
            setError(null);
            return {
                ...current,
                member: renamedDialogSnapshot.members[0],
                metricEquivalenceGroups:
                    renamedDialogSnapshot.metric_equivalence_groups ?? [],
                metricAttachments: renamedDialogSnapshot.metric_attachments ?? [],
            };
        });
    };

    const saveMemberDialog = () => {
        if (!memberDialog) return;
        const { mode, member, originalMember } = memberDialog;
        const nameError = validateSemanticMemberName(
            workingSnapshot,
            mode === "edit" ? originalMember : member,
            member.member_name,
        );
        if (nameError) {
            setError(nameError);
            return;
        }
        const requiredFieldError = validateNewSemanticMemberFields(
            member,
            mode !== "edit" || pendingNewMemberIds.includes(originalMember.member_id),
        );
        if (requiredFieldError) {
            setError(requiredFieldError);
            return;
        }

        updateWorkingSnapshot((current) => {
            let nextSnapshot = current;
            if (mode === "edit") {
                nextSnapshot = renameSemanticMemberReferences(
                    current,
                    originalMember,
                    member,
                );
            } else {
                nextSnapshot = {
                    ...current,
                    members: [...current.members, member],
                };
            }
            return {
                ...nextSnapshot,
                metric_equivalence_groups: memberDialog.metricEquivalenceGroups,
                metric_attachments: memberDialog.metricAttachments,
            };
        });

        if (mode === "edit" && originalMember.member_id !== member.member_id) {
            setPendingNewMemberIds((currentIds) =>
                renamePendingSemanticMemberId(
                    currentIds,
                    originalMember.member_id,
                    member.member_id,
                ),
            );
            setReplacedMemberIds((currentIds) =>
                currentIds.includes(originalMember.member_id)
                    ? currentIds
                    : [...currentIds, originalMember.member_id],
            );
        }
        if (mode !== "edit") {
            setPendingNewMemberIds((currentIds) => [
                ...new Set([...currentIds, member.member_id]),
            ]);
        }
        setSelectedId(member.member_id);
        setError(null);
        closeMemberDialog();
    };

    const closeCreateDialog = (restoreFocus = true) => {
        setCreateMemberType(null);
        setCreateCubeName("");
        if (restoreFocus) requestAnimationFrame(() => createTriggerRef.current?.focus());
    };

    const handleCreateDialogKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
        if (event.key === "Escape") {
            event.preventDefault();
            closeCreateDialog();
            return;
        }
        if (event.key !== "Tab") return;

        const focusableElements = Array.from(
            createDialogRef.current?.querySelectorAll<HTMLElement>(
                CREATE_DIALOG_FOCUSABLE_SELECTOR,
            ) ?? [],
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
        if (createMemberType) cancelButtonRef.current?.focus();
    }, [createMemberType]);

    const requestCreateMember = (
        memberType: CreateMemberType,
        trigger: HTMLButtonElement,
    ) => {
        createTriggerRef.current = trigger;
        setCreateMemberType(memberType);
        setCreateCubeName(defaultCubeName(semanticCubeOptions(workingSnapshot)));
    };

    const createMember = (memberType: CreateMemberType, cubeName: string) => {
        if (!cubeName) {
            setError("当前语义模型没有可用 Cube，无法创建成员。");
            return;
        }
        const member = createDraftSemanticMember(workingSnapshot, memberType, cubeName);
        const trigger = createTriggerRef.current;
        closeCreateDialog(false);
        openMemberDialog("create", member, trigger);
    };

    const refreshDraft = async (draftId: string) => {
        const response = await getSemanticDraft(draftId);
        setDraft(response);
        setSnapshot(response.snapshot);
        setDirty(false);
    };

    const perform = async (
        action: () => Promise<SemanticOperation>,
        success: string,
    ): Promise<SemanticOperation | null> => {
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
            return result;
        } catch (actionError) {
            setError(formatSemanticModelError(actionError));
            return null;
        } finally {
            setBusy(false);
        }
    };

    const save = async () => {
        const invalidMember = workingSnapshot.members
            .map((member) => ({
                member,
                message: validateSemanticMemberName(
                    workingSnapshot,
                    member,
                    member.member_name,
                ),
            }))
            .find((item) => item.message);
        if (invalidMember?.message) {
            setError(
                `${invalidMember.member.title || invalidMember.member.member_name}：${invalidMember.message}`,
            );
            return;
        }
        const missingRequiredField = workingSnapshot.members
            .map((member) => ({
                member,
                message: validateNewSemanticMemberFields(
                    member,
                    pendingNewMemberIds.includes(member.member_id),
                ),
            }))
            .find((item) => item.message);
        if (missingRequiredField?.message) {
            setError(
                `${missingRequiredField.member.title || missingRequiredField.member.member_name}：${missingRequiredField.message}`,
            );
            return;
        }
        const reason = "更新指标和维度治理草稿";
        const payload = asPayload(workingSnapshot, reason);
        const editableDraftStatuses = new Set(["draft", "rejected"]);
        const result = await perform(async () => {
            if (draft && editableDraftStatuses.has(draft.status)) return updateSemanticDraft(draft.draft_id, payload);
            return createSemanticDraft(payload);
        }, "");
        if (result && result.status !== "failed") {
            setPendingNewMemberIds([]);
        }
    };

    const requireDraft = () => {
        if (!draft) {
            setError("请先保存草稿，再执行校验或流转操作。");
            return null;
        }
        return draft;
    };

    const handleRollback = (release: SemanticRelease) => {
        if (dirty && !window.confirm("当前指标治理草稿尚未保存，回滚会丢失修改，确定继续吗？")) return;
        const reason = window.prompt(`请输入回滚 ${release.release_version} 的原因`);
        if (!reason?.trim()) return;
        void perform(() => rollbackSemanticRelease(release.release_version, { reason: reason.trim() }), "");
    };

    const changeFilters = (nextFilters: Filters) => {
        if (dirty && !window.confirm("当前指标治理草稿尚未保存，切换筛选会丢失修改，确定继续吗？")) return;
        requestGateRef.current.start();
        setDraft(null);
        setDirty(false);
        setPendingNewMemberIds([]);
        setReplacedMemberIds([]);
        setPublishBlocked(false);
        setFilters(nextFilters);
    };

    const refresh = () => {
        if (dirty && !window.confirm("当前指标治理草稿尚未保存，刷新会丢失修改，确定继续吗？")) return;
        requestGateRef.current.start();
        setDraft(null);
        setDirty(false);
        setPendingNewMemberIds([]);
        setReplacedMemberIds([]);
        setPublishBlocked(false);
        void load();
    };

    const currentDraft = draft?.snapshot ?? snapshot;
    const activeRelease = releases.find((item) => item.active);
    const activeSnapshotReady = !activeRelease || activeSnapshot.release_version === activeRelease.release_version;
    const canPublish = draft?.status === "validated" && !dirty && !loading && !snapshotUnavailable && !publishBlocked && (!activeRelease || activeSnapshot.release_version === activeRelease.release_version);
    const canRollback = !loading && !snapshotUnavailable && activeSnapshotReady;
    const hasValidationErrors = operationIssues(operation).some((issue) => issue.severity === "error");
    const changeSummary = canPublish && activeSnapshotReady
        ? buildSemanticChangeSummary(activeRelease ? activeSnapshot : emptySnapshot, currentDraft)
        : null;
    const handlePublish = async () => {
        const current = requireDraft();
        if (!current || !canPublish) return;
        const publishConflictMessage = "发布版本已发生变化，请刷新后重试。";
        setBusy(true);
        try {
            const latestReleaseResponse = await listSemanticReleases();
            const latestActiveRelease = latestReleaseResponse.items.find((item) => item.active);
            const latestActiveVersion = latestActiveRelease?.release_version ?? null;
            const pageActiveVersion = activeRelease?.release_version ?? null;
            const pageSnapshotVersion = activeRelease ? activeSnapshot.release_version : null;
            if (latestActiveVersion !== pageActiveVersion || pageSnapshotVersion !== latestActiveVersion) {
                setPublishBlocked(true);
                await load();
                setError(publishConflictMessage);
                setBusy(false);
                return;
            }
        } catch {
            setPublishBlocked(true);
            await load();
            setError("发布版本复核失败，请刷新后重试。");
            setBusy(false);
            return;
        }
        await perform(() => publishSemanticDraft(current.draft_id, { reason: "发布语义模型版本" }), "");
        setBusy(false);
    };
    const normalizedQuery = filters.query.trim().toLowerCase();
    const visibleMembers = currentDraft.members.filter((member) => {
        if (!semanticMemberTypesForBuildTab(activeTab).includes(member.member_type)) return false;
        if (filters.memberType !== "all" && member.member_type !== filters.memberType) return false;
        if (!normalizedQuery) return true;
        return [member.title, member.member_name, member.cube_name]
            .some((value) => value.toLowerCase().includes(normalizedQuery));
    });
    const handleTabChange = (tab: SemanticBuildTab) => {
        setActiveTab(tab);
        setFilters((current) => ({ ...current, memberType: "all" }));
    };
    const handleMemberTypeChange = (memberType: Filters["memberType"]) => {
        if (memberType !== "all" && !semanticMemberTypesForBuildTab(activeTab).includes(memberType)) return;
        changeFilters({ ...filters, memberType });
    };
    return (
        <div id="semantic-model-page" className="relative flex min-h-0 flex-1 flex-col bg-paper">
            <header className="flex min-h-16 shrink-0 items-center justify-between border-b border-ink/10 bg-white px-5 lg:px-7">
                <div className="flex min-w-0 items-center gap-4"><button type="button" onClick={onBack} disabled={busy} title="返回问数工作台" aria-label="返回问数工作台" className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-ink/60 hover:bg-ink/5 disabled:opacity-40"><ArrowLeft className="h-4 w-4" aria-hidden="true" /></button><div className="min-w-0"><p className="font-serif text-xl font-bold text-ink">Agent 管理</p></div></div>
                <div className="flex items-center gap-3"><span className="hidden text-xs text-ink/50 lg:inline">生效版本：<span className="font-mono text-ink">{releases.find((item) => item.active)?.release_version ?? "暂无"}</span></span><button id="semantic-model-refresh" type="button" onClick={refresh} disabled={loading || busy} title="刷新建设数据" aria-label="刷新建设数据" className="grid h-10 w-10 place-items-center rounded-full text-ink/60 hover:bg-ink/5 disabled:opacity-40"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden="true" /></button></div>
            </header>
            {error && <div role="alert" className="border-b border-oxide/20 bg-oxide/5 px-6 py-3 text-sm text-oxide">{error}</div>}
            <AgentManagementTabs activeTab={activeTab} onChange={handleTabChange} disabled={busy} />
            <SemanticBuildToolbar tab={activeTab} query={filters.query} memberType={filters.memberType} count={visibleMembers.length} disabled={busy || loading || snapshotUnavailable} onQueryChange={(query) => setFilters((current) => ({ ...current, query }))} onMemberTypeChange={handleMemberTypeChange} onRefresh={refresh} onCreate={requestCreateMember} />
            <div className="min-h-0 flex-1 overflow-auto">
                {activeTab === "metrics" ? <MetricBuildTable items={visibleMembers} loading={loading} error={error} disabled={busy || loading || snapshotUnavailable} onEdit={(memberId, trigger) => openEditMember(memberId, trigger)} onCopy={(memberId, trigger) => openCopyMember(memberId, trigger)} /> : <DimensionBuildTable items={visibleMembers} loading={loading} error={error} disabled={busy || loading || snapshotUnavailable} onEdit={(memberId, trigger) => openEditMember(memberId, trigger)} onCopy={(memberId, trigger) => openCopyMember(memberId, trigger)} />}
                <div className="border-b border-ink/10 bg-paper">
                    <div className="px-5 py-6 lg:px-7">
                        <SemanticValidationPanel issues={operationIssues(operation)} status={draft?.status ?? null} changeSummary={changeSummary ?? undefined} />
                    </div>
                    <SemanticReleasePanel releases={releases} activeVersion={activeRelease?.release_version ?? null} activeSnapshot={snapshotUnavailable || !activeSnapshotReady ? null : activeSnapshot} />
                    <SemanticVersionActionBar
                        releases={releases}
                        draftStatus={draft?.status ?? null}
                        dirty={dirty}
                        busy={busy}
                        canReview={draft?.status === "pending_review"}
                        canPublish={canPublish}
                        canRollback={canRollback}
                        hasValidationErrors={hasValidationErrors}
                        onSave={save}
                        onValidate={() => { const current = requireDraft(); if (current) void perform(() => validateSemanticDraft(current.draft_id), ""); }}
                        onSubmit={() => { const current = requireDraft(); if (current) void perform(() => submitSemanticDraft(current.draft_id, { reason: "提交语义模型审核" }), ""); }}
                        onReview={(decision) => { const current = requireDraft(); if (current) void perform(() => reviewSemanticDraft(current.draft_id, { decision, reason: decision === "approved" ? "审核通过" : "审核驳回" }), ""); }}
                        onPublish={() => void handlePublish()}
                        onRollback={handleRollback}
                    />
                </div>
            </div>
            {memberDialog && (
                <SemanticMemberEditDialog
                    mode={memberDialog.mode}
                    member={memberDialog.member}
                    snapshot={currentDraft}
                    members={currentDraft.members}
                    dependencyCandidates={semanticDependencyCandidates(
                        {
                            ...currentDraft,
                            members: memberDialog.mode === "edit"
                                ? currentDraft.members.map((item) => item.member_id === memberDialog.originalMember.member_id ? memberDialog.member : item)
                                : [...currentDraft.members, memberDialog.member],
                        },
                        memberDialog.member.member_id,
                    )}
                    metricEquivalenceGroups={memberDialog.metricEquivalenceGroups}
                    metricAttachments={memberDialog.metricAttachments}
                    disabled={busy || loading || snapshotUnavailable}
                    error={error}
                    onCancel={closeMemberDialog}
                    onSave={saveMemberDialog}
                    onChange={(member) => setMemberDialog((current) => current ? { ...current, member } : current)}
                    onMemberNameChange={changeMemberName}
                    onRelationsChange={(groups, attachments) => setMemberDialog((current) => current ? {
                        ...current,
                        metricEquivalenceGroups: groups,
                        metricAttachments: attachments,
                    } : current)}
                />
            )}
            {createMemberType && (
                <div className="absolute inset-0 z-20 flex items-start justify-center bg-ink/10 p-10" role="presentation">
                    <div
                        ref={createDialogRef}
                        className="w-full max-w-xl border border-ink/15 bg-white p-6 shadow-line"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="create-member-title"
                        onKeyDown={handleCreateDialogKeyDown}
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
                                <button ref={cancelButtonRef} type="button" onClick={() => closeCreateDialog()} className="min-h-10 border border-ink/15 px-4 text-sm font-semibold text-ink/65 transition hover:bg-paper focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40">
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
