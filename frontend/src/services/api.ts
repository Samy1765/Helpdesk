/**
 * Thin fetch wrapper: JSON in/out, bearer token, one transparent refresh on 401.
 * Tokens live in localStorage (wrapped in try/catch: storage may be unavailable).
 */

const BASE = "/api/v1";
const ACCESS = "pai.access";
const REFRESH = "pai.refresh";

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string | null) {
  try { value === null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch { /* ignore */ }
}

export const tokens = {
  get access() { return read(ACCESS); },
  set(access: string, refresh: string) { write(ACCESS, access); write(REFRESH, refresh); },
  clear() { write(ACCESS, null); write(REFRESH, null); },
  get refresh() { return read(REFRESH); },
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

async function tryRefresh(): Promise<boolean> {
  const refresh = tokens.refresh;
  if (!refresh) return false;
  const r = await fetch(`${BASE}/auth/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!r.ok) return false;
  const body = await r.json();
  tokens.set(body.access_token, body.refresh_token);
  return true;
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) {
      const first = d[0] as { msg?: string; loc?: unknown[] };
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
      return `${field ? field + ": " : ""}${(first.msg || fallback).replace(/^Value error, /, "")}`;
    }
  }
  return fallback;
}

export async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const access = tokens.access;
  if (access) headers.set("Authorization", `Bearer ${access}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401 && retry && path !== "/auth/login" && (await tryRefresh())) {
    return request<T>(path, init, false);
  }
  if (res.status === 401 && path !== "/auth/login") {
    tokens.clear();
    onUnauthorized?.();
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, errorMessage(body, res.statusText || "Request failed"));
  return body as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T,>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
};

export async function downloadAttachment(token: string, filename: string) {
  const res = await fetch(`${BASE}/attachments/${token}`, { headers: { Authorization: `Bearer ${tokens.access}` } });
  if (!res.ok) return;
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export function clientEnvironment(): Record<string, string> {
  const nav = navigator as Navigator & { userAgentData?: { platform?: string } };
  return {
    platform: nav.userAgentData?.platform || navigator.platform || "unknown",
    user_agent: navigator.userAgent.slice(0, 200),
    language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    online: String(navigator.onLine),
  };
}
