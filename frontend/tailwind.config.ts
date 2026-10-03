/**
 * Tailwind CSS 主题配置
 * 「数字账房」设计基座：冷白数据终端色板，衬线报表字体
 */
import type { Config } from "tailwindcss";

export default {
    content: ["./index.html", "./src/**/*.{ts,tsx}"],
    theme: {
        extend: {
            fontFamily: {
                sans: [
                    '"Noto Sans SC"',
                    '"PingFang SC"',
                    '"Hiragino Sans GB"',
                    '"Microsoft YaHei"',
                    "sans-serif",
                ],
                serif: [
                    '"Noto Serif SC"',
                    '"Source Han Serif SC"',
                    '"Songti SC"',
                    "SimSun",
                    "serif",
                ],
                mono: ['"JetBrains Mono"', '"SFMono-Regular"', "Consolas", "monospace"],
            },
            colors: {
                paper: "#F5F7FA",
                canvas: "#EAF0F4",
                workbench: "#EEF7FB",
                ink: "#1F2937",
                dai: "#155E75",
                cinnabar: "#0E7490",
                pine: "#21856F",
                indigo: "#256D85",
                amber: "#C47A18",
                oxide: "#C24156",
            },
            boxShadow: {
                line: "0 1px 2px rgba(31, 41, 55, 0.08), 0 6px 16px rgba(31, 41, 55, 0.07)",
                panel: "0 24px 70px rgba(15, 61, 76, 0.14)",
            },
        },
    },
    plugins: [],
} satisfies Config;
