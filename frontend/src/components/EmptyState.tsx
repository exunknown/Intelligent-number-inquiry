/**
 * 首页空状态组件
 * 「数字账房」首屏：印章字标、品牌水印与示例问题
 */
import { ArrowUpRight } from "lucide-react";

type EmptyStateProps = {
    examples: string[];
    onUseExample: (example: string) => void;
};

export function EmptyState({ examples, onUseExample }: EmptyStateProps) {
    return (
        <div className="relative mx-auto flex min-h-full max-w-4xl flex-col overflow-hidden px-4 py-8 sm:py-12">
            {/* 品牌水印：超大「答」字微倾锚在右下角，与印章「慧」拼出品牌名 */}
            <span
                aria-hidden="true"
                className="rise-in pointer-events-none absolute -bottom-10 -right-10 hidden rotate-3 select-none font-serif text-[16rem] font-black leading-none text-ink/[0.08] sm:block"
                style={{ animationDelay: "360ms" }}
            >
                答
            </span>

            {/* my-auto：内容矮时垂直居中，超出时从顶部自然排布，避免居中裁切 */}
            <div className="my-auto">
                <div className="flex items-center gap-4 sm:gap-5">
                    <div className="seal-in relative grid h-16 w-16 shrink-0 -rotate-2 place-items-center bg-indigo/15 text-indigo shadow-line sm:h-20 sm:w-20">
                        <span
                            className="pointer-events-none absolute inset-[5px] border border-indigo/30"
                            aria-hidden="true"
                        />
                        <span className="font-serif text-3xl font-bold leading-none sm:text-4xl">
                            慧
                        </span>
                    </div>
                    <div className="rise-in">
                        <h1 className="font-serif text-6xl font-black leading-tight tracking-wide text-ink sm:text-8xl">
                            慧答
                        </h1>
                        <div className="mt-2 flex items-center gap-2 sm:mt-3">
                            <span className="h-1.5 w-1.5 bg-cinnabar" aria-hidden="true" />
                            <p className="font-mono text-[11px] text-ink/45">
                                HUIDA · 数字账房
                            </p>
                        </div>
                    </div>
                </div>

                <div className="mt-10 sm:mt-12">
                    <div
                        className="rise-in mb-3 flex items-center gap-3"
                        style={{ animationDelay: "180ms" }}
                    >
                        <span className="text-sm font-semibold text-ink/55">从这些问题开始</span>
                        <span className="h-px flex-1 bg-ink/10" aria-hidden="true" />
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                        {examples.map((example, i) => (
                            <button
                                key={example}
                                type="button"
                                onClick={() => onUseExample(example)}
                                className="rise-in group flex items-start gap-3 rounded-xl border border-ink/15 bg-white px-4 py-3.5 text-left shadow-line transition hover:-translate-y-0.5 hover:border-cinnabar/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/35 sm:py-4"
                                style={{ animationDelay: `${210 + i * 60}ms` }}
                            >
                                <span className="mt-1 font-mono text-[11px] font-medium text-cinnabar/70">
                                    {String(i + 1).padStart(2, "0")}
                                </span>
                                <span className="flex-1 font-serif text-[15px] leading-7 text-ink/80">
                                    {example}
                                </span>
                                <ArrowUpRight
                                    className="mt-1 h-4 w-4 shrink-0 text-ink/25 transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-cinnabar"
                                    aria-hidden="true"
                                />
                            </button>
                        ))}
                    </div>
                </div>

                <div
                    className="rise-in mt-7 flex items-center justify-between border-t border-ink/10 pt-4 font-mono text-[11px] text-ink/40 sm:mt-9"
                    style={{ animationDelay: "480ms" }}
                >
                    <span>TEXT → SQL → TABLE</span>
                    <span>每一步都可复核</span>
                </div>
            </div>
        </div>
    );
}
