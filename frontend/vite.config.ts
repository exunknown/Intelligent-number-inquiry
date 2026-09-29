/**
 * Vite 开发与构建配置
 * 包含 React 插件和后端 API 开发代理
 */
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      // 5173 落在 Windows Hyper-V/WSL2 端口排除范围，使用本地开发白名单中的 3000。
      port: 3000,
      proxy: {
        "/api": {
          target: backend,
          changeOrigin: true,
        },
      },
    },
  };
});
