/**
 * Keycloak 浏览器认证适配器
 * 令牌仅保存在适配器内存中，不写入浏览器持久化存储。
 */
import Keycloak from "keycloak-js";

let keycloak: Keycloak | null = null;
let initPromise: Promise<boolean> | null = null;

function requiredEnvironmentValue(name: keyof ImportMetaEnv) {
    const value = import.meta.env[name]?.trim();
    if (!value) {
        throw new Error(`缺少前端认证配置：${name}`);
    }
    return value;
}

function getKeycloak() {
    if (!keycloak) {
        keycloak = new Keycloak({
            url: requiredEnvironmentValue("VITE_KEYCLOAK_URL"),
            realm: requiredEnvironmentValue("VITE_KEYCLOAK_REALM"),
            clientId: requiredEnvironmentValue("VITE_KEYCLOAK_CLIENT_ID"),
        });
    }
    return keycloak;
}

export function initAuth() {
    if (!initPromise) {
        initPromise = getKeycloak().init({
            onLoad: "login-required",
            pkceMethod: "S256",
            checkLoginIframe: false,
        });
    }
    return initPromise;
}

export async function getAccessToken() {
    const client = getKeycloak();
    try {
        await client.updateToken(30);
    } catch {
        throw new Error("登录已失效，请重新登录");
    }
    if (!client.token) {
        throw new Error("登录已失效，请重新登录");
    }
    return client.token;
}

export function getUsername() {
    const claims = getKeycloak().tokenParsed;
    for (const value of [claims?.preferred_username, claims?.name, claims?.email]) {
        if (typeof value === "string" && value.trim()) {
            return value.trim();
        }
    }
    return "已登录用户";
}

export async function logout() {
    await getKeycloak().logout({ redirectUri: window.location.origin });
}
