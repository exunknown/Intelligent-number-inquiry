import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import {
    validateSemanticMemberName,
    type SemanticMember,
    type SemanticMetricAttachment,
    type SemanticMetricEquivalenceGroup,
    type SemanticSnapshot,
} from "../lib/semanticModel";
import { SemanticMetricRelationsEditor } from "./SemanticMetricRelationsEditor";

type SemanticMemberEditorProps = {
    member: SemanticMember | null;
    snapshot: Pick<SemanticSnapshot, "members">;
    disabled: boolean;
    onChange: (member: SemanticMember) => void;
    onMemberNameChange: (memberName: string) => void;
    members: SemanticMember[];
    metricEquivalenceGroups: SemanticMetricEquivalenceGroup[];
    metricAttachments: SemanticMetricAttachment[];
    onRelationsChange: (groups: SemanticMetricEquivalenceGroup[], attachments: SemanticMetricAttachment[]) => void;
    onSave: () => void;
};

const inputClass = "h-10 w-full border border-ink/15 bg-white px-3 text-sm text-ink outline-none focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:bg-paper disabled:text-ink/50";
const areaClass = "min-h-24 w-full resize-y border border-ink/15 bg-white px-3 py-2 text-sm leading-6 text-ink outline-none focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:bg-paper disabled:text-ink/50";

export function SemanticMemberEditor({
    member,
    snapshot,
    disabled,
    onChange,
    onMemberNameChange,
    members,
    metricEquivalenceGroups,
    metricAttachments,
    onRelationsChange,
    onSave,
}: SemanticMemberEditorProps) {
    const [memberNameDraft, setMemberNameDraft] = useState(member?.member_name ?? "");

    useEffect(() => {
        setMemberNameDraft(member?.member_name ?? "");
    }, [member?.member_id, member?.member_name]);

    const memberNameError = member
        ? validateSemanticMemberName(snapshot, member, memberNameDraft)
        : null;

    if (!member) {
        return <div className="grid min-h-0 flex-1 place-items-center text-sm text-ink/45">从左侧选择一个成员开始编辑。</div>;
    }

    const update = (patch: Partial<SemanticMember>) => onChange({ ...member, ...patch });
    const updateMeasure = (patch: Partial<NonNullable<SemanticMember["measure"]>>) => update({ measure: { ...member.measure, ...patch } as NonNullable<SemanticMember["measure"]> });
    const updateDimension = (patch: Partial<NonNullable<SemanticMember["dimension"]>>) => update({ dimension: { ...member.dimension, ...patch } as NonNullable<SemanticMember["dimension"]> });

    return (
        <section className="min-h-0 flex-1 overflow-y-auto bg-[#eceee8]">
            <div className="mx-auto max-w-4xl p-6 lg:p-8">
                <div className="mb-6 flex items-start justify-between gap-6">
                    <div>
                        <div className="flex items-center gap-2 text-xs text-indigo">
                            <span>{member.cube_name}</span><span className="text-ink/30">/</span><span>{member.member_type === "measure" ? "指标" : member.member_type === "time_dimension" ? "时间维度" : "维度"}</span>
                        </div>
                        <h2 className="mt-2 font-serif text-2xl font-bold text-ink">{member.title || member.member_name}</h2>
                        <p className="mt-1 font-mono text-xs text-ink/45">{member.member_name} · {member.member_id}</p>
                    </div>
                    <button type="button" onClick={onSave} disabled={disabled || Boolean(memberNameError)} className="inline-flex min-h-10 shrink-0 items-center gap-2 bg-dai px-4 text-sm font-semibold text-paper transition hover:bg-indigo disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/50">
                        <Save className="h-4 w-4" aria-hidden="true" />保存草稿
                    </button>
                </div>

                <div className="grid gap-5 xl:grid-cols-2">
                    <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">{member.member_type === "measure" ? "指标名称" : "展示名称"}</span>
                        <input className={inputClass} value={member.title} disabled={disabled} onChange={(event) => update({ title: event.target.value })} />
                    </label>
                    <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">
                            成员编码 <span className="font-normal text-ink/45">（必填）</span>
                        </span>
                        <input
                            className={`${inputClass} ${memberNameError ? "border-oxide focus:border-oxide focus:ring-oxide/15" : ""}`}
                            value={memberNameDraft}
                            disabled={disabled}
                            onChange={(event) => setMemberNameDraft(event.target.value)}
                            onBlur={() => {
                                if (
                                    !memberNameError &&
                                    memberNameDraft !== member.member_name
                                ) {
                                    onMemberNameChange(memberNameDraft);
                                }
                            }}
                            aria-invalid={Boolean(memberNameError)}
                            aria-describedby="member-name-help member-name-error"
                        />
                        <span id="member-name-help" className="mt-1 block text-xs text-ink/45">
                            仅支持字母、数字和下划线
                        </span>
                        {memberNameError && (
                            <span id="member-name-error" role="alert" className="mt-1 block text-xs text-oxide">
                                {memberNameError}
                            </span>
                        )}
                    </label>
                    <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">数据类型</span>
                        <input className={inputClass} value={member.member_type === "time_dimension" ? "date" : member.data_type} disabled={disabled || member.member_type === "time_dimension"} onChange={(event) => update({ data_type: event.target.value })} />
                    </label>
                    <label className="block xl:col-span-2">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">业务描述</span>
                        <textarea className={areaClass} value={member.description} disabled={disabled} onChange={(event) => update({ description: event.target.value })} />
                    </label>
                    <label className="block xl:col-span-2">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">AI 上下文</span>
                        <textarea className={areaClass} value={member.ai_context} disabled={disabled} onChange={(event) => update({ ai_context: event.target.value })} />
                    </label>
                    <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">
                            源字段 ID <span className="font-normal text-ink/45">（必填）</span>
                        </span>
                        <input required className={inputClass} value={member.source_column_id ?? ""} disabled={disabled} onChange={(event) => update({ source_column_id: event.target.value || null })} />
                    </label>
                    <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">别名</span>
                        <input className={inputClass} value={member.aliases.join("、")} disabled={disabled} onChange={(event) => update({ aliases: event.target.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) })} />
                    </label>
                    <div className="flex items-center gap-5 border-y border-ink/10 py-3 text-sm text-ink/70 xl:col-span-2">
                        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={member.filterable} disabled={disabled} onChange={(event) => update({ filterable: event.target.checked })} />可筛选</label>
                        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={member.groupable} disabled={disabled} onChange={(event) => update({ groupable: event.target.checked })} />可分组</label>
                    </div>

                    {member.member_type === "measure" && member.measure && (
                        <div className="border-t-2 border-indigo/30 pt-4 xl:col-span-2">
                            <p className="mb-4 font-serif font-bold text-ink">指标口径</p>
                            <div className="grid gap-5 xl:grid-cols-2">
                                <label className="block"><span className="mb-2 block text-xs font-semibold text-ink/60">聚合方式</span><select className={inputClass} value={member.measure.aggregation_type} disabled={disabled} onChange={(event) => updateMeasure({ aggregation_type: event.target.value as NonNullable<SemanticMember["measure"]>["aggregation_type"] })}><option value="sum">求和</option><option value="count">计数</option><option value="count_distinct">去重计数</option><option value="number">表达式结果</option></select></label>
                                <label className="block"><span className="mb-2 block text-xs font-semibold text-ink/60">依赖成员</span><input className={inputClass} value={member.measure.dependency_members.join("、")} disabled={disabled} onChange={(event) => updateMeasure({ dependency_members: event.target.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) })} /></label>
                                <label className="block xl:col-span-2"><span className="mb-2 block text-xs font-semibold text-ink/60">表达式 <span className="font-normal text-ink/45">（必填）</span></span><textarea required className={`${areaClass} font-mono text-xs`} value={member.measure.expression} disabled={disabled} onChange={(event) => updateMeasure({ expression: event.target.value })} /></label>
                            </div>
                        </div>
                    )}

                    {member.member_type === "measure" && (
                        <SemanticMetricRelationsEditor
                            member={member}
                            members={members}
                            groups={metricEquivalenceGroups}
                            attachments={metricAttachments}
                            disabled={disabled}
                            onChange={onRelationsChange}
                        />
                    )}

                    {member.member_type !== "measure" && member.dimension && (
                        <div className="border-t-2 border-pine/30 pt-4 xl:col-span-2">
                            <p className="mb-4 font-serif font-bold text-ink">维度属性</p>
                            <div className="grid gap-5 xl:grid-cols-2">
                                <label className="block"><span className="mb-2 block text-xs font-semibold text-ink/60">维度类型</span><select className={inputClass} value={member.dimension.dimension_type} disabled={disabled || member.member_type === "time_dimension"} onChange={(event) => updateDimension({ dimension_type: event.target.value as NonNullable<SemanticMember["dimension"]>["dimension_type"] })}>{member.member_type === "time_dimension" ? <option value="time">时间</option> : <><option value="string">文本</option><option value="number">数值</option><option value="time">时间</option></>}</select></label>
                                {member.member_type === "time_dimension" && (
                                    <label className="block">
                                        <span className="mb-2 block text-xs font-semibold text-ink/60">时间粒度</span>
                                        <select className={inputClass} value={member.dimension.time_granularity ?? "day"} disabled={disabled} onChange={(event) => updateDimension({ time_granularity: event.target.value })}>
                                            <option value="day">日</option>
                                            <option value="week">周</option>
                                            <option value="month">月</option>
                                            <option value="quarter">季度</option>
                                            <option value="year">年</option>
                                        </select>
                                    </label>
                                )}
                                <label className="inline-flex items-center gap-2 text-sm text-ink/70"><input type="checkbox" checked={member.dimension.primary_key} disabled={disabled} onChange={(event) => updateDimension({ primary_key: event.target.checked })} />主键维度</label>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
}
