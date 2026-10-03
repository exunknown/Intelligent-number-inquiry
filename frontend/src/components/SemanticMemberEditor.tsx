import { useEffect, useState } from "react";
import {
    resolveSemanticDependencyMemberIds,
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
    memberNameValidationId: string;
    members: SemanticMember[];
    dependencyCandidates: SemanticMember[];
    metricEquivalenceGroups: SemanticMetricEquivalenceGroup[];
    metricAttachments: SemanticMetricAttachment[];
    onRelationsChange: (groups: SemanticMetricEquivalenceGroup[], attachments: SemanticMetricAttachment[]) => void;
    showActions?: boolean;
};

const inputClass = "h-11 w-full rounded-xl border border-ink/15 bg-white px-4 text-sm text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:bg-paper disabled:text-ink/50";
const areaClass = "min-h-28 w-full resize-y rounded-xl border border-ink/15 bg-white px-4 py-3 text-sm leading-6 text-ink outline-none transition focus:border-indigo/60 focus:ring-2 focus:ring-indigo/15 disabled:bg-paper disabled:text-ink/50";
const dataTypeOptions = [
    ["string", "文本"],
    ["number", "数值"],
    ["date", "日期"],
    ["datetime", "日期时间"],
    ["timestamp", "时间戳"],
] as const;

export function SemanticMemberEditor({
    member,
    snapshot,
    disabled,
    onChange,
    onMemberNameChange,
    memberNameValidationId,
    members,
    dependencyCandidates,
    metricEquivalenceGroups,
    metricAttachments,
    onRelationsChange,
}: SemanticMemberEditorProps) {
    const [memberNameDraft, setMemberNameDraft] = useState(member?.member_name ?? "");

    useEffect(() => {
        setMemberNameDraft(member?.member_name ?? "");
    }, [member?.member_id, member?.member_name]);

    const memberNameError = member
        ? validateSemanticMemberName(
              snapshot,
              member,
              memberNameDraft,
              memberNameValidationId,
          )
        : null;

    if (!member) {
        return <div className="grid min-h-0 place-items-center p-8 text-sm text-ink/45">请选择一个成员。</div>;
    }

    const update = (patch: Partial<SemanticMember>) => onChange({ ...member, ...patch });
    const updateMeasure = (patch: Partial<NonNullable<SemanticMember["measure"]>>) => update({ measure: { ...member.measure, ...patch } as NonNullable<SemanticMember["measure"]> });
    const updateDimension = (patch: Partial<NonNullable<SemanticMember["dimension"]>>) => update({ dimension: { ...member.dimension, ...patch } as NonNullable<SemanticMember["dimension"]> });
    const dependencyResolution = resolveSemanticDependencyMemberIds(member, snapshot);
    const preservedResolvedDependencyIds = dependencyResolution.memberIds.filter((memberId) => !dependencyCandidates.some((candidate) => candidate.member_id === memberId));
    const selectedDataType = member.member_type === "time_dimension" ? "date" : member.data_type;
    const hasKnownDataType = dataTypeOptions.some(([value]) => value === selectedDataType);

    return (
        <div className="p-8">
            <div className="mx-auto max-w-4xl">
                <div className="mb-6">
                    <div>
                        <div className="flex items-center gap-2 text-xs text-indigo">
                            <span>{member.cube_name}</span><span className="text-ink/30">/</span><span>{member.member_type === "measure" ? "指标" : member.member_type === "time_dimension" ? "时间维度" : "维度"}</span>
                        </div>
                        <h2 className="mt-2 font-serif text-2xl font-bold text-ink">{member.title || member.member_name}</h2>
                        <p className="mt-1 font-mono text-xs text-ink/45">{member.member_name} · {member.member_id}</p>
                    </div>
                </div>

                <div className="grid gap-5 xl:grid-cols-2">
                    <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">{member.member_type === "measure" ? "指标名称" : "展示名称"}</span>
                        <input className={inputClass} value={member.title} placeholder="请输入展示名称" disabled={disabled} onChange={(event) => update({ title: event.target.value })} />
                    </label>
                    <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">
                            成员编码 <span className="font-normal text-ink/45">（必填）</span>
                        </span>
                        <input
                            className={`${inputClass} ${memberNameError ? "border-oxide focus:border-oxide focus:ring-oxide/15" : ""}`}
                            value={memberNameDraft}
                            placeholder="请输入成员编码"
                            disabled={disabled}
                            onChange={(event) => {
                                const nextMemberName = event.target.value;
                                setMemberNameDraft(nextMemberName);
                                onMemberNameChange(nextMemberName);
                            }}
                            onBlur={() => {
                                if (memberNameDraft !== member.member_name) {
                                    onMemberNameChange(memberNameDraft);
                                }
                            }}
                            aria-invalid={Boolean(memberNameError)}
                            aria-required="true"
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
                        <select className={inputClass} value={selectedDataType} disabled={disabled || member.member_type === "time_dimension"} onChange={(event) => update({ data_type: event.target.value })}>
                            {!hasKnownDataType && <option value={selectedDataType}>{selectedDataType}（当前值）</option>}
                            {dataTypeOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                    </label>
                    <label className="block xl:col-span-2">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">业务描述</span>
                        <textarea className={areaClass} value={member.description} placeholder="补充业务口径、统计范围或使用说明" disabled={disabled} onChange={(event) => update({ description: event.target.value })} />
                    </label>
                    <label className="block xl:col-span-2">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">AI 上下文</span>
                        <textarea className={areaClass} value={member.ai_context} placeholder="补充问数模型需要理解的业务上下文" disabled={disabled} onChange={(event) => update({ ai_context: event.target.value })} />
                    </label>
                    <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-ink/60">
                            源字段 ID <span className="font-normal text-ink/45">（必填）</span>
                        </span>
                        <input required aria-required="true" className={inputClass} value={member.source_column_id ?? ""} placeholder="请输入源字段 ID" disabled={disabled} onChange={(event) => update({ source_column_id: event.target.value || null })} />
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
                        <div className="rounded-2xl border border-indigo/15 bg-indigo/5 p-5 xl:col-span-2">
                            <p className="mb-4 font-serif font-bold text-ink">指标口径</p>
                            <div className="grid gap-5 xl:grid-cols-2">
                                <label className="block"><span className="mb-2 block text-xs font-semibold text-ink/60">聚合方式</span><select className={inputClass} value={member.measure.aggregation_type} disabled={disabled} onChange={(event) => updateMeasure({ aggregation_type: event.target.value as NonNullable<SemanticMember["measure"]>["aggregation_type"] })}><option value="sum">求和</option><option value="count">计数</option><option value="count_distinct">去重计数</option><option value="number">表达式结果</option></select></label>
                                <label className="block">
                                    <span className="mb-2 block text-xs font-semibold text-ink/60">依赖成员</span>
                                    <select
                                        className={`${inputClass} h-28 py-2`}
                                        multiple
                                        value={dependencyResolution.memberIds}
                                        disabled={disabled}
                                        onChange={(event) => updateMeasure({
                                            dependency_members: Array.from(new Set([
                                                ...preservedResolvedDependencyIds,
                                                ...Array.from(event.target.selectedOptions, (option) => option.value),
                                                ...dependencyResolution.unresolved,
                                            ])),
                                        })}
                                    >
                                        {dependencyCandidates.map((item) => (
                                            <option key={item.member_id} value={item.member_id}>
                                                {item.title || item.member_name} · {item.member_name} · {item.cube_name}
                                            </option>
                                        ))}
                                    </select>
                                    {dependencyResolution.unresolved.length > 0 && (
                                        <span role="alert" className="mt-2 block text-xs text-oxide">
                                            未解析的依赖将保留：{dependencyResolution.unresolved.join("、")}
                                        </span>
                                    )}
                                </label>
                                <label className="block xl:col-span-2"><span className="mb-2 block text-xs font-semibold text-ink/60">表达式 <span className="font-normal text-ink/45">（必填）</span></span><textarea required aria-required="true" className={`${areaClass} font-mono text-xs`} value={member.measure.expression} placeholder="请输入指标计算表达式" disabled={disabled} onChange={(event) => updateMeasure({ expression: event.target.value })} /></label>
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
                        <div className="rounded-2xl border border-pine/15 bg-pine/5 p-5 xl:col-span-2">
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
        </div>
    );
}
