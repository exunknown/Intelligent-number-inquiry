import { Link2, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import {
    removeMetricAttachment,
    setMetricEquivalenceMembership,
    upsertMetricAttachment,
    type SemanticMetricAttachment,
    type SemanticMetricAttachmentRelationType,
    type SemanticMetricEquivalenceGroup,
    type SemanticMember,
} from "../lib/semanticModel";

type SemanticMetricRelationsEditorProps = {
    member: SemanticMember;
    members: SemanticMember[];
    groups: SemanticMetricEquivalenceGroup[];
    attachments: SemanticMetricAttachment[];
    disabled: boolean;
    onChange: (groups: SemanticMetricEquivalenceGroup[], attachments: SemanticMetricAttachment[]) => void;
};

const inputClass = "h-9 w-full border border-ink/15 bg-white px-2.5 text-xs text-ink outline-none focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:bg-paper disabled:text-ink/50";
const relationLabels: Record<SemanticMetricAttachmentRelationType, string> = {
    supporting: "支撑指标",
    comparison: "对比指标",
    efficiency: "效率指标",
    breakdown: "拆解指标",
};

function relationSnapshot(
    groups: SemanticMetricEquivalenceGroup[],
    attachments: SemanticMetricAttachment[],
) {
    return {
        release_version: "draft",
        cubes: [],
        joins: [],
        members: [],
        metric_equivalence_groups: groups,
        metric_attachments: attachments,
    };
}

export function SemanticMetricRelationsEditor({
    member,
    members,
    groups,
    attachments,
    disabled,
    onChange,
}: SemanticMetricRelationsEditorProps) {
    const metricMembers = useMemo(
        () => members.filter((item) => item.member_type === "measure"),
        [members],
    );
    const currentGroup = groups.find((group) =>
        group.members.some((item) => item.member_id === member.member_id),
    );
    const currentMembership = currentGroup?.members.find(
        (item) => item.member_id === member.member_id,
    );
    const [attachedMemberId, setAttachedMemberId] = useState("");
    const [relationType, setRelationType] = useState<SemanticMetricAttachmentRelationType>("supporting");
    const [relationNote, setRelationNote] = useState("");
    const [relationOrder, setRelationOrder] = useState(0);
    const [relationVisible, setRelationVisible] = useState(false);
    const currentAttachments = attachments
        .filter((item) => item.primary_member_id === member.member_id)
        .sort((left, right) => left.display_order - right.display_order);
    const attachedIds = new Set(currentAttachments.map((item) => item.attached_member_id));
    const availableMembers = metricMembers.filter(
        (item) => item.member_id !== member.member_id && !attachedIds.has(item.member_id),
    );

    const updateRelations = (
        nextGroups: SemanticMetricEquivalenceGroup[],
        nextAttachments: SemanticMetricAttachment[],
    ) => onChange(nextGroups, nextAttachments);

    const updateEquivalence = (
        groupId: string | null,
        canonical: boolean,
        matchType = currentMembership?.match_type ?? "exact",
        note = currentMembership?.note ?? "",
    ) => {
        const next = setMetricEquivalenceMembership(
            relationSnapshot(groups, attachments),
            member.member_id,
            groupId,
            matchType,
            canonical,
            note,
        );
        updateRelations(next.metric_equivalence_groups ?? [], next.metric_attachments ?? []);
    };

    const addAttachment = () => {
        if (!attachedMemberId) return;
        const next = upsertMetricAttachment(relationSnapshot(groups, attachments), {
            primary_member_id: member.member_id,
            attached_member_id: attachedMemberId,
            relation_type: relationType,
            display_order: relationOrder,
            default_visible: relationVisible,
            note: relationNote,
        });
        updateRelations(next.metric_equivalence_groups ?? [], next.metric_attachments ?? []);
        setAttachedMemberId("");
        setRelationNote("");
    };

    const updateAttachment = (attachment: SemanticMetricAttachment, patch: Partial<SemanticMetricAttachment>) => {
        const next = upsertMetricAttachment(relationSnapshot(groups, attachments), { ...attachment, ...patch });
        updateRelations(next.metric_equivalence_groups ?? [], next.metric_attachments ?? []);
    };

    const deleteAttachment = (attachment: SemanticMetricAttachment) => {
        const next = removeMetricAttachment(
            relationSnapshot(groups, attachments),
            attachment.primary_member_id,
            attachment.attached_member_id,
        );
        updateRelations(next.metric_equivalence_groups ?? [], next.metric_attachments ?? []);
    };

    return (
        <section className="border-t-2 border-cinnabar/30 pt-4 xl:col-span-2">
            <div className="flex items-center gap-2">
                <Link2 className="h-4 w-4 text-cinnabar" aria-hidden="true" />
                <div>
                    <p className="font-serif font-bold text-ink">指标关系</p>
                    <p className="mt-1 text-xs text-ink/50">指标代码：<span className="font-mono text-ink/70">{member.member_name}</span></p>
                </div>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-2">
                <div className="border border-ink/10 bg-white p-3">
                    <p className="text-xs font-semibold text-ink/65">等效指标组</p>
                    <select
                        className={`${inputClass} mt-2`}
                        value={currentGroup?.group_id ?? ""}
                        disabled={disabled}
                        onChange={(event) => updateEquivalence(event.target.value || null, false)}
                    >
                        <option value="">不加入等效组</option>
                        {groups.map((group) => <option key={group.group_id} value={group.group_id}>{group.group_name || group.group_id}</option>)}
                    </select>
                    {currentGroup && <>
                        <label className="mt-3 block text-xs text-ink/65">
                            <span className="mb-1 block">等效成员类型</span>
                            <select
                                className={inputClass}
                                value={currentMembership?.match_type ?? "exact"}
                                disabled={disabled}
                                onChange={(event) => updateEquivalence(currentGroup.group_id, currentGroup.canonical_member_id === member.member_id, event.target.value as "exact" | "compatible")}
                            >
                                <option value="exact">精确等效</option>
                                <option value="compatible">兼容等效</option>
                            </select>
                        </label>
                        <label className="mt-3 flex items-center gap-2 text-xs text-ink/65">
                            <input type="checkbox" checked={currentGroup.canonical_member_id === member.member_id} disabled={disabled} onChange={(event) => updateEquivalence(currentGroup.group_id, event.target.checked)} />
                            设为标准成员
                        </label>
                    </>}
                    {!groups.length && <p className="mt-2 text-xs text-ink/45">当前版本暂无可选等效指标组。</p>}
                </div>

                <div className="border border-ink/10 bg-white p-3">
                    <p className="text-xs font-semibold text-ink/65">附带指标</p>
                    {currentAttachments.length === 0 && <p className="mt-2 text-xs text-ink/45">暂无附带指标。</p>}
                    <div className="mt-2 space-y-2">
                        {currentAttachments.map((attachment) => {
                            const attached = metricMembers.find((item) => item.member_id === attachment.attached_member_id);
                            return <div key={attachment.attached_member_id} className="border border-ink/10 bg-paper p-2">
                                <div className="flex items-center justify-between gap-2">
                                    <span className="truncate text-xs font-semibold text-ink">{attached?.title || attached?.member_name || attachment.attached_member_id}</span>
                                    <button type="button" onClick={() => deleteAttachment(attachment)} disabled={disabled} title="移除附带指标" aria-label="移除附带指标" className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-oxide hover:bg-oxide/10 disabled:opacity-45"><Trash2 className="h-3.5 w-3.5" aria-hidden="true" /></button>
                                </div>
                                <div className="mt-2 grid grid-cols-[1fr_4.5rem] gap-2">
                                    <select className={inputClass} value={attachment.relation_type} disabled={disabled} aria-label={`${attached?.title || attached?.member_name || attachment.attached_member_id}的关系类型`} onChange={(event) => updateAttachment(attachment, { relation_type: event.target.value as SemanticMetricAttachmentRelationType })}>{Object.entries(relationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                                    <input className={inputClass} type="number" min="0" value={attachment.display_order} disabled={disabled} aria-label="关系顺序" onChange={(event) => updateAttachment(attachment, { display_order: Number(event.target.value) || 0 })} />
                                </div>
                                <input className={`${inputClass} mt-2`} value={attachment.note} disabled={disabled} placeholder="关系说明" aria-label="关系说明" onChange={(event) => updateAttachment(attachment, { note: event.target.value })} />
                                <label className="mt-2 flex items-center gap-2 text-xs text-ink/65"><input type="checkbox" checked={attachment.default_visible} disabled={disabled} onChange={(event) => updateAttachment(attachment, { default_visible: event.target.checked })} />默认展示</label>
                            </div>;
                        })}
                    </div>
                    <div className="mt-3 border-t border-ink/10 pt-3">
                        <div className="grid grid-cols-[1fr_5rem] gap-2">
                            <select className={inputClass} value={attachedMemberId} disabled={disabled} onChange={(event) => setAttachedMemberId(event.target.value)} aria-label="选择附带指标">
                                <option value="">选择附带指标</option>
                                {availableMembers.map((item) => <option key={item.member_id} value={item.member_id}>{item.title || item.member_name}</option>)}
                            </select>
                            <input className={inputClass} type="number" min="0" value={relationOrder} disabled={disabled} aria-label="新增关系顺序" onChange={(event) => setRelationOrder(Number(event.target.value) || 0)} />
                        </div>
                        <div className="mt-2 grid grid-cols-[1fr_auto] gap-2">
                            <input className={inputClass} value={relationNote} disabled={disabled} placeholder="关系说明" aria-label="新增关系说明" onChange={(event) => setRelationNote(event.target.value)} />
                            <button type="button" onClick={addAttachment} disabled={disabled || !attachedMemberId} className="inline-flex min-h-9 items-center gap-1 border border-indigo/30 px-2.5 text-xs font-semibold text-indigo hover:bg-indigo/5 disabled:opacity-45"><Plus className="h-3.5 w-3.5" aria-hidden="true" />添加</button>
                        </div>
                        <label className="mt-2 flex items-center gap-2 text-xs text-ink/65"><input type="checkbox" checked={relationVisible} disabled={disabled} onChange={(event) => setRelationVisible(event.target.checked)} />新增关系默认展示</label>
                    </div>
                </div>
            </div>
        </section>
    );
}
