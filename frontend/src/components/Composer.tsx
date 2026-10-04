/**
 * 聊天输入区组件
 * 处理问题输入、发送和停止当前流式请求（账台录入条：聚焦时底线变朱）
 */
import { ArrowUp, Square, WandSparkles } from "lucide-react";
import { FormEvent, KeyboardEvent, useEffect, useRef } from "react";
import { cn } from "../lib/format";

type ComposerProps = {
    value: string;
    disabled: boolean;
    isStreaming: boolean;
    onChange: (value: string) => void;
    onSubmit: () => void;
    onStop: () => void;
};

export function Composer({
    value,
    disabled,
    isStreaming,
    onChange,
    onSubmit,
    onStop,
}: ComposerProps) {
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    // 输入框随内容自动增高（上限与 max-h-36 一致），清空时回落到单行
    useEffect(() => {
        const textarea = textareaRef.current;
        if (!textarea) return;
        textarea.style.height = "auto";
        textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
    }, [value]);

    const submit = (event: FormEvent) => {
        event.preventDefault();
        if (!disabled) onSubmit();
    };

    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!disabled) onSubmit();
        }
    };

    return (
        <form
            onSubmit={submit}
            className="border-t border-ink/10 bg-paper px-4 py-4"
        >
            <div className="mx-auto flex max-w-4xl items-end gap-3 rounded-xl border border-ink/15 bg-white p-2 shadow-panel transition focus-within:border-cinnabar/50 focus-within:ring-2 focus-within:ring-cinnabar/15">
                <div className="hidden h-11 w-11 shrink-0 place-items-center rounded-lg bg-indigo/10 text-indigo sm:grid">
                    <WandSparkles className="h-5 w-5" aria-hidden="true" />
                </div>
                <textarea
                    ref={textareaRef}
                    value={value}
                    onChange={(event) => onChange(event.target.value)}
                    onKeyDown={onKeyDown}
                    rows={1}
                    placeholder="问一笔账，例如：2025 年第一季度各大区 GMV 排名"
                    className="max-h-36 min-h-11 flex-1 resize-none bg-transparent px-2 py-3 text-[15px] leading-6 text-ink outline-none placeholder:text-ink/35"
                />
                <button
                    type={isStreaming ? "button" : "submit"}
                    onClick={isStreaming ? onStop : undefined}
                    disabled={!isStreaming && disabled}
                    className={cn(
                        "grid h-11 w-11 shrink-0 place-items-center rounded-full text-paper transition focus:outline-none focus:ring-2 focus:ring-cinnabar/40 focus:ring-offset-2",
                        isStreaming
                            ? "bg-oxide hover:bg-oxide/90"
                            : "bg-cinnabar hover:bg-[#0B6178] disabled:cursor-not-allowed disabled:bg-cinnabar/30",
                    )}
                    title={isStreaming ? "停止" : "发送"}
                    aria-label={isStreaming ? "停止" : "发送"}
                >
                    {isStreaming ? (
                        <Square
                            className="h-4 w-4 fill-current"
                            aria-hidden="true"
                        />
                    ) : (
                        <ArrowUp className="h-5 w-5" aria-hidden="true" />
                    )}
                </button>
            </div>
        </form>
    );
}
