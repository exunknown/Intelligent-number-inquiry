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
