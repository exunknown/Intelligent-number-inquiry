/**
 * React 应用入口
 * 挂载根组件并加载全局样式
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { getUsername, initAuth } from "./auth/keycloak";
import "./styles.css";

const root = createRoot(document.getElementById("root")!);

function AuthLoading() {
    return (
        <main className="grid h-dvh place-items-center bg-paper px-6 text-ink">
            <p className="text-sm text-ink/60" role="status">
                正在检查登录状态...
            </p>
        </main>
    );
}

function AuthFailure() {
    return (
        <main className="grid h-dvh place-items-center bg-paper px-6 text-center text-ink">
            <div>
                <h1 className="font-serif text-2xl font-bold">无法完成登录</h1>
                <p className="mt-2 text-sm text-ink/60" role="alert">
                    请检查认证服务是否可用，然后重新尝试。
                </p>
                <button
                    type="button"
                    className="mt-6 h-11 rounded-lg bg-cinnabar px-5 text-sm font-semibold text-paper transition hover:bg-[#ad3a26] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cinnabar/60 focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
                    onClick={() => window.location.reload()}
                >
                    重新登录
                </button>
            </div>
        </main>
    );
}

async function bootstrap() {
    root.render(<AuthLoading />);
    try {
        const authenticated = await initAuth();
        if (!authenticated) {
            throw new Error("authentication was not established");
        }
        root.render(
            <StrictMode>
                <App username={getUsername()} />
            </StrictMode>,
        );
    } catch {
        root.render(<AuthFailure />);
    }
}

void bootstrap();
