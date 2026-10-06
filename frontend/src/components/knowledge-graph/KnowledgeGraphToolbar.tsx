import { Database, Layers3, Network, Search, Table2 } from "lucide-react";
import type {
    KnowledgeGraphRelease,
    KnowledgeGraphScenario,
    KnowledgeGraphView,
} from "../../lib/knowledgeGraph";

export type KnowledgeGraphWorkspace = "ontology" | KnowledgeGraphView;

type KnowledgeGraphToolbarProps = {
    releases: KnowledgeGraphRelease[];
    selectedRelease: string;
    backend: "mysql" | "neo4j";
    workspace: KnowledgeGraphWorkspace;
    scenario: KnowledgeGraphScenario;
    search: string;
    onReleaseChange: (releaseVersion: string) => void;
    onWorkspaceChange: (workspace: KnowledgeGraphWorkspace) => void;
    onScenarioChange: (scenario: KnowledgeGraphScenario) => void;
    onSearchChange: (value: string) => void;
};

const scenarios: Array<[KnowledgeGraphScenario, string]> = [
    ["product", "商品经营"],
    ["customer", "客群偏好"],
    ["region", "区域热销"],
    ["metric", "指标证据"],
];

export function KnowledgeGraphToolbar({
    releases,
    selectedRelease,
    backend,
    workspace,
    scenario,
    search,
    onReleaseChange,
    onWorkspaceChange,
    onScenarioChange,
    onSearchChange,
}: KnowledgeGraphToolbarProps) {
    return (
        <div className="border-b border-ink/10 bg-white px-5 py-4 lg:px-7">
            <div className="flex flex-wrap items-end gap-3">
                <label className="min-w-[250px] flex-1 text-xs font-semibold text-ink/60">
                    <span className="mb-1.5 block">图谱版本</span>
                    <select
                        value={selectedRelease}
                        onChange={(event) => onReleaseChange(event.target.value)}
                        className="h-10 w-full rounded-md border border-ink/15 bg-paper px-3 text-sm font-normal text-ink outline-none transition focus:border-cinnabar/60 focus:ring-2 focus:ring-cinnabar/15"
                    >
                        {releases.map((release) => (
                            <option key={release.release_version} value={release.release_version}>
                                {release.release_version}{release.active ? " · 当前" : ""}
                            </option>
                        ))}
                    </select>
                </label>
                <div className="flex min-h-10 items-center gap-2 rounded-md border border-ink/10 bg-paper px-3 text-xs text-ink/65">
                    <Database className="h-4 w-4 text-cinnabar" aria-hidden="true" />
                    <span>{backend === "neo4j" ? "Neo4j 查询" : "Meta MySQL 查询"}</span>
                </div>
                <label className="relative min-w-[220px] flex-1 text-xs font-semibold text-ink/60 lg:max-w-[300px]">
                    <span className="sr-only">搜索图谱</span>
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35" aria-hidden="true" />
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => onSearchChange(event.target.value)}
                        placeholder="搜索节点名称或编号"
                        className="h-10 w-full rounded-md border border-ink/15 bg-paper pl-9 pr-3 text-sm font-normal text-ink outline-none transition focus:border-cinnabar/60 focus:ring-2 focus:ring-cinnabar/15"
                    />
                </label>
            </div>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-1 rounded-md border border-ink/10 bg-paper p-1" role="tablist" aria-label="知识图谱视图">
                    {([
                        ["ontology", "本体底座", Layers3],
                        ["relation", "关系图", Network],
                        ["schema", "Schema 图谱", Table2],
                    ] as const).map(([value, label, Icon]) => (
                        <button
                            key={value}
                            type="button"
                            role="tab"
                            aria-selected={workspace === value}
                            onClick={() => onWorkspaceChange(value)}
                            className={`inline-flex min-h-9 items-center gap-2 rounded px-3 text-xs font-semibold transition ${workspace === value ? "bg-ink text-white" : "text-ink/55 hover:bg-white hover:text-ink"}`}
                        >
                            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                            {label}
                        </button>
                    ))}
                </div>
                <div className="flex items-center gap-1 overflow-x-auto" role="tablist" aria-label="关系图场景">
                    {scenarios.map(([value, label]) => (
                        <button
                            key={value}
                            type="button"
                            onClick={() => onScenarioChange(value)}
                            aria-pressed={scenario === value}
                            className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold transition ${scenario === value ? "bg-cinnabar text-white" : "text-ink/55 hover:bg-cinnabar/10 hover:text-cinnabar"}`}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
