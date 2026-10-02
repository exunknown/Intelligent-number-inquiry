export type SemanticMemberType = "measure" | "dimension" | "time_dimension";
export type SemanticMetricEquivalenceMatchType = "exact" | "compatible";
export type SemanticMetricAttachmentRelationType =
    | "supporting"
    | "comparison"
    | "efficiency"
    | "breakdown";

export type SemanticMeasure = {
    expression: string;
    aggregation_type: "sum" | "count" | "count_distinct" | "number";
    dependency_members: string[];
};

export type SemanticDimension = {
    dimension_type: "string" | "number" | "time";
    time_granularity: string | null;
    primary_key: boolean;
};

export type SemanticMember = {
    release_version: string;
    member_id: string;
    cube_name: string;
    member_name: string;
    member_type: SemanticMemberType;
    title: string;
    description: string;
    data_type: string;
    source_column_id: string | null;
    ai_context: string;
    aliases: string[];
    filterable: boolean;
    groupable: boolean;
    status: string;
    calculation_note: string;
    unit: string;
    measure?: SemanticMeasure | null;
    dimension?: SemanticDimension | null;
};

export type SemanticMemberSummary = Pick<
    SemanticMember,
    | "member_id"
    | "cube_name"
    | "member_name"
    | "member_type"
    | "title"
    | "description"
    | "data_type"
    | "source_column_id"
    | "aliases"
    | "filterable"
    | "groupable"
    | "calculation_note"
    | "unit"
>;

export type SemanticMetricEquivalenceMember = {
    member_id: string;
    match_type: SemanticMetricEquivalenceMatchType;
    note: string;
};

export type SemanticMetricEquivalenceGroup = {
    group_id: string;
    canonical_member_id: string;
    group_name: string;
    description: string;
    members: SemanticMetricEquivalenceMember[];
};

export type SemanticMetricAttachment = {
    primary_member_id: string;
    attached_member_id: string;
    relation_type: SemanticMetricAttachmentRelationType;
    display_order: number;
    default_visible: boolean;
    note: string;
};

export type SemanticCube = {
    release_version: string;
    cube_name: string;
    sql_table: string;
    title: string;
    description: string;
    public: boolean;
};

export type SemanticJoin = {
    release_version: string;
    cube_name: string;
    target_cube_name: string;
    sql_expression: string;
    relationship: string;
    editable: boolean;
};

export type SemanticSnapshot = {
    release_version: string;
    cubes: SemanticCube[];
    joins: SemanticJoin[];
    members: SemanticMember[];
    metric_equivalence_groups?: SemanticMetricEquivalenceGroup[];
    metric_attachments?: SemanticMetricAttachment[];
};

export type SemanticDraft = {
    draft_id: string;
    release_version: string;
    status: string;
    snapshot: SemanticSnapshot & { reason?: string };
    review_note: string | null;
    updated_at: string | null;
};

export type SemanticOperation = {
    operation_id: string;
    status: string;
    draft_id: string | null;
    release_version: string | null;
    error_code: string | null;
    issues: SemanticValidationIssue[];
};

export type SemanticValidationIssue = {
    code: string;
    path: string;
    message: string;
    severity: "error" | "warning";
};

export type SemanticRelease = {
    release_version: string;
    status: string;
    active: boolean;
    error_code: string | null;
    snapshot?: SemanticSnapshot & { reason?: string };
};

export type SemanticDependencyResolution = {
    memberIds: string[];
    unresolved: string[];
};

export type SemanticChangeSummary = {
    added: SemanticMember[];
    changed: SemanticMember[];
    removed: SemanticMember[];
    equivalence_changed: boolean;
    attachments_changed: boolean;
    has_changes: boolean;
};

type SemanticMemberDirectoryFilters = {
    memberType: "all" | SemanticMemberType;
    query: string;
};

export function buildSemanticMemberId(
    member: Pick<SemanticMember, "member_type" | "cube_name" | "member_name">,
): string {
    return `${member.member_type}:${member.cube_name}:${member.member_name}`;
}

export function semanticCubeOptions(
    snapshot: Pick<SemanticSnapshot, "cubes">,
): SemanticCube[] {
    return snapshot.cubes;
}

export function createDraftSemanticMember(
    snapshot: Pick<SemanticSnapshot, "release_version" | "cubes" | "members">,
    memberType: "measure" | "dimension" | "time_dimension",
    cubeName?: string,
): SemanticMember {
    const cube = cubeName
        ? snapshot.cubes.find((item) => item.cube_name === cubeName)
        : snapshot.cubes.find((item) => item.public) ??
          snapshot.cubes.find((item) => item.cube_name === "ecommerce") ??
          snapshot.cubes[0];
    if (cubeName && !cube) {
        throw new Error(`指定 Cube 不存在：${cubeName}`);
    }
    if (!cube) {
        throw new Error("当前语义模型没有可用 Cube，无法创建成员。");
    }
    const resolvedCubeName = cube.cube_name;
    const prefix =
        memberType === "measure"
            ? "new_metric"
            : memberType === "time_dimension"
              ? "new_time_dimension"
              : "new_dimension";
    let sequence = 1;
    while (
        snapshot.members.some(
            (member) =>
                member.cube_name === resolvedCubeName &&
                member.member_name === `${prefix}_${sequence}`,
        )
    ) {
        sequence += 1;
    }
    const memberName = `${prefix}_${sequence}`;
    const isMeasure = memberType === "measure";
    const isTimeDimension = memberType === "time_dimension";

    return {
        release_version: snapshot.release_version,
        member_id: buildSemanticMemberId({
            member_type: memberType,
            cube_name: resolvedCubeName,
            member_name: memberName,
        }),
        cube_name: resolvedCubeName,
        member_name: memberName,
        member_type: memberType,
        title: isMeasure
            ? `新指标 ${sequence}`
            : isTimeDimension
              ? `新时间维度 ${sequence}`
              : `新维度 ${sequence}`,
        description: "",
        data_type: isMeasure ? "number" : isTimeDimension ? "date" : "string",
        source_column_id: null,
        ai_context: "",
        aliases: [],
        filterable: !isMeasure,
        groupable: !isMeasure,
        status: "draft",
        calculation_note: "",
        unit: "",
        measure: isMeasure
            ? { expression: "", aggregation_type: "sum", dependency_members: [] }
            : null,
        dimension: isMeasure
            ? null
            : {
                  dimension_type: isTimeDimension ? "time" : "string",
                  time_granularity: isTimeDimension ? "day" : null,
                  primary_key: false,
              },
    };
}

export function resolveSemanticDependencyMemberIds(
    member: Pick<SemanticMember, "member_id" | "cube_name" | "member_type" | "measure">,
    snapshot: Pick<SemanticSnapshot, "members">,
): SemanticDependencyResolution {
    const measureMembers = snapshot.members.filter((item) => item.member_type === "measure");
    const membersById = new Map(measureMembers.map((item) => [item.member_id, item]));
    const membersByQualifiedName = new Map(
        measureMembers.flatMap((item) => [
            [`${item.cube_name}.${item.member_name}`, item],
            [`${item.cube_name}:${item.member_name}`, item],
        ]),
    );
    const memberIds: string[] = [];
    const unresolved: string[] = [];
    const resolvedIds = new Set<string>();
    const unresolvedValues = new Set<string>();

    for (const rawValue of member.measure?.dependency_members ?? []) {
        const candidate =
            membersById.get(rawValue) ??
            membersByQualifiedName.get(rawValue) ??
            measureMembers.find(
                (item) =>
                    item.cube_name === member.cube_name &&
                    item.member_name === rawValue,
            );
        if (!candidate) {
            if (!unresolvedValues.has(rawValue)) {
                unresolved.push(rawValue);
                unresolvedValues.add(rawValue);
            }
            continue;
        }
        if (candidate.member_id === member.member_id || resolvedIds.has(candidate.member_id)) {
            continue;
        }
        memberIds.push(candidate.member_id);
        resolvedIds.add(candidate.member_id);
    }

    return { memberIds, unresolved };
}

export function semanticDependencyCandidates(
    snapshot: Pick<SemanticSnapshot, "members">,
    currentMemberId: string,
): SemanticMember[] {
    const currentMember = snapshot.members.find((item) => item.member_id === currentMemberId);
    const cubeName = currentMember?.cube_name ?? currentMemberId.split(":")[1];
    return snapshot.members.filter(
        (item) =>
            item.member_type === "measure" &&
            item.cube_name === cubeName &&
            item.member_id !== currentMemberId,
    );
}

export function copySemanticMeasure(
    snapshot: SemanticSnapshot,
    memberId: string,
): { snapshot: SemanticSnapshot; copiedMemberId: string } {
    const nextSnapshot = cloneSemanticSnapshot(snapshot);
    const sourceMember = nextSnapshot.members.find((item) => item.member_id === memberId);
    if (!sourceMember || sourceMember.member_type !== "measure" || !sourceMember.measure) {
        throw new Error("只能复制指标成员。");
    }

    let sequence = 1;
    let copiedName = `${sourceMember.member_name}_copy_${sequence}`;
    while (
        nextSnapshot.members.some(
            (item) =>
                item.cube_name === sourceMember.cube_name &&
                item.member_name === copiedName,
        )
    ) {
        sequence += 1;
        copiedName = `${sourceMember.member_name}_copy_${sequence}`;
    }
    const copiedMemberId = buildSemanticMemberId({
        ...sourceMember,
        member_name: copiedName,
    });
    const copiedMember: SemanticMember = {
        ...structuredClone(sourceMember),
        member_id: copiedMemberId,
        member_name: copiedName,
        title: sourceMember.title ? `${sourceMember.title} 副本` : `${copiedName} 副本`,
        status: "draft",
    };
    nextSnapshot.members.push(copiedMember);

    nextSnapshot.metric_equivalence_groups = (nextSnapshot.metric_equivalence_groups ?? []).map(
        (group) => {
            const sourceRelation = group.members.find(
                (item) => item.member_id === memberId,
            );
            if (!sourceRelation && group.canonical_member_id !== memberId) return group;
            if (group.members.some((item) => item.member_id === copiedMemberId)) return group;
            return {
                ...group,
                members: [
                    ...group.members,
                    {
                        member_id: copiedMemberId,
                        match_type: sourceRelation?.match_type ?? "exact",
                        note: sourceRelation?.note ?? "",
                    },
                ],
            };
        },
    );

    const originalAttachments = nextSnapshot.metric_attachments ?? [];
    const attachments: SemanticMetricAttachment[] = [];
    for (const attachment of originalAttachments) {
        if (
            attachment.primary_member_id !== memberId &&
            attachment.attached_member_id !== memberId
        ) {
            continue;
        }
        attachments.push({
            ...attachment,
            primary_member_id:
                attachment.primary_member_id === memberId
                    ? copiedMemberId
                    : attachment.primary_member_id,
            attached_member_id:
                attachment.attached_member_id === memberId
                    ? copiedMemberId
                    : attachment.attached_member_id,
        });
    }
    attachments.push(...originalAttachments);
    const uniqueAttachments = new Map<string, SemanticMetricAttachment>();
    for (const attachment of attachments) {
        const endpointKey = `${attachment.primary_member_id}\u0000${attachment.attached_member_id}`;
        if (!uniqueAttachments.has(endpointKey)) uniqueAttachments.set(endpointKey, attachment);
    }
    nextSnapshot.metric_attachments = [...uniqueAttachments.values()];

    return { snapshot: nextSnapshot, copiedMemberId };
}

function sortedRelationSignature(value: unknown): string {
    if (Array.isArray(value)) {
        return JSON.stringify(
            value.map((item) => sortedRelationSignature(item)).sort(),
        );
    }
    if (value !== null && typeof value === "object") {
        return JSON.stringify(
            Object.fromEntries(
                Object.entries(value)
                    .sort(([left], [right]) => left.localeCompare(right))
                    .map(([key, item]) => [key, sortedRelationSignature(item)]),
            ),
        );
    }
    return JSON.stringify(value);
}

function measureDefinitionSignature(member: SemanticMember): string {
    return JSON.stringify({
        expression: member.measure?.expression ?? null,
        aggregation_type: member.measure?.aggregation_type ?? null,
        dependency_members: [...(member.measure?.dependency_members ?? [])].sort(),
        source_column_id: member.source_column_id ?? null,
        data_type: member.data_type ?? null,
    });
}

export function buildSemanticChangeSummary(
    base: Pick<SemanticSnapshot, "members" | "metric_equivalence_groups" | "metric_attachments">,
    current: Pick<SemanticSnapshot, "members" | "metric_equivalence_groups" | "metric_attachments">,
): SemanticChangeSummary {
    const baseMembers = new Map(base.members.map((member) => [member.member_id, member]));
    const currentMembers = new Map(
        current.members.map((member) => [member.member_id, member]),
    );
    const added = current.members.filter((member) => !baseMembers.has(member.member_id));
    const removed = base.members.filter((member) => {
        const currentMember = currentMembers.get(member.member_id);
        return (
            currentMember === undefined ||
            (member.status === "published" && currentMember.status !== "published")
        );
    });
    const changed = current.members.filter((member) => {
        const previous = baseMembers.get(member.member_id);
        const isOffline = previous?.status === "published" && member.status !== "published";
        return (
            previous !== undefined &&
            !isOffline &&
            member.member_type === "measure" &&
            measureDefinitionSignature(previous) !== measureDefinitionSignature(member)
        );
    });
    const equivalence_changed =
        sortedRelationSignature(base.metric_equivalence_groups ?? []) !==
        sortedRelationSignature(current.metric_equivalence_groups ?? []);
    const attachments_changed =
        sortedRelationSignature(base.metric_attachments ?? []) !==
        sortedRelationSignature(current.metric_attachments ?? []);

    return {
        added,
        changed,
        removed,
        equivalence_changed,
        attachments_changed,
        has_changes:
            added.length > 0 ||
            changed.length > 0 ||
            removed.length > 0 ||
            equivalence_changed ||
            attachments_changed,
    };
}

export function validateSemanticMemberName(
    snapshot: Pick<SemanticSnapshot, "members">,
    member: Pick<SemanticMember, "member_id" | "cube_name">,
    memberName: string,
): string | null {
    if (!memberName.trim()) return "成员编码不能为空";
    if (!/^[A-Za-z0-9_]+$/.test(memberName)) {
        return "成员编码只能包含字母、数字和下划线";
    }
    if (
        snapshot.members.some(
            (item) =>
                item.member_id !== member.member_id &&
                item.cube_name === member.cube_name &&
                item.member_name === memberName,
        )
    ) {
        return "同一 Cube 内成员编码不能重复";
    }
    return null;
}

export function validateNewSemanticMemberFields(
    member: Pick<
        SemanticMember,
        "member_type" | "source_column_id" | "measure"
    >,
    isNewMember: boolean,
): string | null {
    if (!isNewMember) return null;
    if (!member.source_column_id?.trim()) return "源字段 ID为必填项";
    if (member.member_type === "measure" && !member.measure?.expression.trim()) {
        return "表达式为必填项";
    }
    return null;
}

export function renamePendingSemanticMemberId(
    pendingMemberIds: readonly string[],
    previousMemberId: string,
    nextMemberId: string,
): string[] {
    return pendingMemberIds.map((memberId) =>
        memberId === previousMemberId ? nextMemberId : memberId,
    );
}

export function renameSemanticMemberReferences(
    snapshot: SemanticSnapshot,
    previousMember: SemanticMember,
    nextMember: SemanticMember,
): SemanticSnapshot {
    const previousQualifiedName = `${previousMember.cube_name}.${previousMember.member_name}`;
    const nextQualifiedName = `${nextMember.cube_name}.${nextMember.member_name}`;
    const bareNameReplacement =
        previousMember.cube_name === nextMember.cube_name
            ? nextMember.member_name
            : nextQualifiedName;
    const replaceDependency = (value: string, dependentCubeName: string): string => {
        if (value === previousMember.member_id) return nextMember.member_id;
        if (value === previousQualifiedName) return nextQualifiedName;
        if (
            value === previousMember.member_name &&
            dependentCubeName === previousMember.cube_name
        ) {
            return bareNameReplacement;
        }
        return value;
    };
    const replaceExpressionReferences = (
        expression: string,
        dependentCubeName: string,
    ): string =>
        expression.replace(/\{([^{}]+)\}/g, (reference, memberReference: string) => {
            if (memberReference === previousQualifiedName) {
                return `{${nextQualifiedName}}`;
            }
            if (
                memberReference === previousMember.member_name &&
                dependentCubeName === previousMember.cube_name
            ) {
                return `{${bareNameReplacement}}`;
            }
            return reference;
        });
    const replaceRelationId = (value: string): string =>
        value === previousMember.member_id ? nextMember.member_id : value;

    return {
        ...snapshot,
        members: snapshot.members.map((member) => {
            const isRenamedMember = member.member_id === previousMember.member_id;
            const nextSnapshotMember = isRenamedMember ? nextMember : member;
            if (!nextSnapshotMember.measure) return nextSnapshotMember;
            const dependentCubeName = isRenamedMember
                ? previousMember.cube_name
                : member.cube_name;
            return {
                ...nextSnapshotMember,
                measure: {
                    ...nextSnapshotMember.measure,
                    expression: replaceExpressionReferences(
                        nextSnapshotMember.measure.expression,
                        dependentCubeName,
                    ),
                    dependency_members: nextSnapshotMember.measure.dependency_members.map(
                        (value) => replaceDependency(value, dependentCubeName),
                    ),
                },
            };
        }),
        metric_equivalence_groups: snapshot.metric_equivalence_groups?.map((group) => ({
            ...group,
            canonical_member_id: replaceRelationId(group.canonical_member_id),
            members: group.members.map((member) => ({
                ...member,
                member_id: replaceRelationId(member.member_id),
            })),
        })),
        metric_attachments: snapshot.metric_attachments?.map((attachment) => ({
            ...attachment,
            primary_member_id: replaceRelationId(attachment.primary_member_id),
            attached_member_id: replaceRelationId(attachment.attached_member_id),
        })),
    };
}

export function mergeSemanticMemberSummaries(
    baseItems: SemanticMemberSummary[],
    workingMembers: SemanticMemberSummary[],
    filters: SemanticMemberDirectoryFilters,
    replacedMemberIds: readonly string[] = [],
): SemanticMemberSummary[] {
    const replacedIds = new Set(replacedMemberIds);
    const members = new Map(
        baseItems
            .filter((item) => !replacedIds.has(item.member_id))
            .map((item) => [item.member_id, item]),
    );
    for (const item of workingMembers) members.set(item.member_id, item);
    const query = filters.query.trim().toLocaleLowerCase();

    return [...members.values()].filter((item) => {
        if (filters.memberType !== "all" && item.member_type !== filters.memberType) return false;
        if (!query) return true;
        const searchable = [
            item.title,
            item.member_name,
            item.description,
            ...(item.aliases ?? []),
            item.source_column_id ?? "",
        ]
            .join(" ")
            .toLocaleLowerCase();
        return searchable.includes(query);
    });
}

export function createMetricEquivalenceGroup(
    snapshot: Pick<SemanticSnapshot, "metric_equivalence_groups">,
): SemanticMetricEquivalenceGroup {
    const groups = snapshot.metric_equivalence_groups ?? [];
    let sequence = 1;
    while (groups.some((group) => group.group_id === `metric-equivalence-${sequence}`)) {
        sequence += 1;
    }
    return {
        group_id: `metric-equivalence-${sequence}`,
        canonical_member_id: "",
        group_name: `新等效指标组 ${sequence}`,
        description: "待完善的等效指标组",
        members: [],
    };
}

export function resolveSemanticModelSnapshot(
    active: SemanticRelease | null | undefined,
    detail?: SemanticRelease | null,
): SemanticSnapshot {
    if (!active) {
        return { release_version: "draft", cubes: [], joins: [], members: [] };
    }
    const snapshot = active.snapshot ?? detail?.snapshot;
    if (!snapshot || snapshot.release_version !== active.release_version) {
        throw new Error("活动语义模型版本缺少快照，无法编辑。");
    }
    return snapshot;
}

export function editorSections(member: Pick<SemanticMember, "member_type">): string[] {
    if (member.member_type === "measure") {
        return ["common", "measure", "source"];
    }
    if (member.member_type === "time_dimension") {
        return ["common", "dimension", "time", "source"];
    }
    return ["common", "dimension", "source"];
}

export function canLeaveSemanticModel({
    isStreaming,
    dirty,
}: {
    isStreaming: boolean;
    dirty: boolean;
}): boolean {
    return !isStreaming && !dirty;
}

export function createSemanticModelRequestGate() {
    let generation = 0;
    return {
        start(): number {
            generation += 1;
            return generation;
        },
        accepts(startedGeneration: number): boolean {
            return startedGeneration === generation;
        },
    };
}

type SemanticError = {
    status?: number;
    code?: string;
    message?: string;
};

export function formatSemanticModelError(error: unknown): string {
    const value =
        error !== null && typeof error === "object"
            ? (error as SemanticError)
            : {};
    if (value.status === 401) return "登录已失效，请重新登录。";
    if (value.status === 403) return "没有指标治理权限，请联系平台管理员。";
    if (value.status === 404) return "指标治理对象不存在，可能已被其他人修改。";
    if (value.status === 409 && value.code === "release_conflict") {
        return "发布版本已发生变化，请刷新后重试。";
    }
    if (value.status === 409) return "草稿状态已变化，请刷新后重试。";
    if (value.status === 422) return "提交内容不符合要求，请检查后重试。";
    if (value.status === 503) return "指标治理服务暂不可用，请稍后重试。";
    if (
        typeof value.message === "string" &&
        value.message.length <= 240 &&
        !/(?:token|secret|password|authorization|bearer|cookie|api[-_]?key)/i.test(
            value.message,
        )
    ) {
        return value.message;
    }
    return "指标治理操作未完成，请稍后重试。";
}

export function newSemanticIdempotencyKey(): string {
    return crypto.randomUUID();
}

export function cloneSemanticSnapshot(snapshot: SemanticSnapshot): SemanticSnapshot {
    return structuredClone(snapshot);
}

export function updateSemanticMemberFields<T extends object>(
    member: T,
    patch: Partial<T>,
): T {
    return { ...member, ...patch };
}

export function setMetricEquivalenceMembership(
    snapshot: SemanticSnapshot,
    memberId: string,
    groupId: string | null,
    matchType: SemanticMetricEquivalenceMatchType,
    canonical: boolean,
    note: string,
): SemanticSnapshot {
    const groups = (snapshot.metric_equivalence_groups ?? [])
        .map((group) => {
            const members = group.members.filter((member) => member.member_id !== memberId);
            if (group.group_id !== groupId) {
                return {
                    ...group,
                    canonical_member_id:
                        group.canonical_member_id === memberId
                            ? members[0]?.member_id ?? ""
                            : group.canonical_member_id,
                    members,
                };
            }

            const nextMembers = [
                ...members,
                { member_id: memberId, match_type: matchType, note },
            ];
            const nextCanonical = canonical
                ? memberId
                : group.canonical_member_id === memberId
                  ? members[0]?.member_id ?? ""
                  : group.canonical_member_id;
            return {
                ...group,
                canonical_member_id: nextCanonical,
                members: nextMembers,
            };
        })
        .filter((group) => group.members.length > 0);

    return { ...snapshot, metric_equivalence_groups: groups };
}

export function upsertMetricAttachment(
    snapshot: SemanticSnapshot,
    attachment: SemanticMetricAttachment,
): SemanticSnapshot {
    const attachments = (snapshot.metric_attachments ?? []).filter(
        (item) =>
            item.primary_member_id !== attachment.primary_member_id ||
            item.attached_member_id !== attachment.attached_member_id,
    );
    return {
        ...snapshot,
        metric_attachments: [...attachments, { ...attachment }],
    };
}

export function removeMetricAttachment(
    snapshot: SemanticSnapshot,
    primaryMemberId: string,
    attachedMemberId: string,
): SemanticSnapshot {
    return {
        ...snapshot,
        metric_attachments: (snapshot.metric_attachments ?? []).filter(
            (attachment) =>
                attachment.primary_member_id !== primaryMemberId ||
                attachment.attached_member_id !== attachedMemberId,
        ),
    };
}

export function serializeSemanticSnapshot(
    snapshot: SemanticSnapshot,
    reason: string,
) {
    return {
        ...snapshot,
        metric_equivalence_groups: snapshot.metric_equivalence_groups ?? [],
        metric_attachments: snapshot.metric_attachments ?? [],
        reason,
    };
}
