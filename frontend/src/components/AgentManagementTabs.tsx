import type { SemanticBuildTab } from "../lib/semanticModel";

export type AgentManagementTabsProps = {
    activeTab: SemanticBuildTab;
    onChange: (tab: SemanticBuildTab) => void;
    disabled?: boolean;
};

export function AgentManagementTabs({ activeTab, onChange, disabled = false }: AgentManagementTabsProps) {
    return (
        <div role="tablist" aria-label="Agent 管理建设类型" className="flex shrink-0 items-center gap-4 bg-white px-5 py-3 lg:px-7">
            {([
                ["metrics", "指标建设", "agent-panel-metrics"],
                ["dimensions", "维度建设", "agent-panel-dimensions"],
            ] as const).map(([tab, label, panelId]) => (
                <button
                    key={tab}
                    id={`agent-tab-${tab}`}
                    type="button"
                    role="tab"
                    aria-controls={panelId}
                    aria-selected={activeTab === tab}
                    disabled={disabled}
                    onClick={() => onChange(tab)}
                    className={`min-h-10 rounded-full px-4 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/40 disabled:cursor-not-allowed disabled:opacity-45 ${activeTab === tab ? "bg-cinnabar text-white" : "text-ink/65 hover:bg-paper hover:text-ink"}`}
                >
                    {label}
                </button>
            ))}
        </div>
    );
}
