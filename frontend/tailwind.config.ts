/**
 * Tailwind CSS 主题配置
 * 「数字账房」设计基座：账纸 / 黛蓝 / 朱砂色板，衬线报表字体
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
                paper: "#F4F5F1",
                ink: "#23282F",
                dai: "#212C3E",
                cinnabar: "#C4402B",
                pine: "#2F7D5C",
                indigo: "#2F4E7A",
                oxide: "#8E3226",
            },
            boxShadow: {
                line: "0 1px 2px rgba(35, 40, 47, 0.08), 0 6px 16px rgba(35, 40, 47, 0.07)",
                panel: "0 24px 70px rgba(33, 44, 62, 0.14)",
            },
        },
    },
    plugins: [],
} satisfies Config;
