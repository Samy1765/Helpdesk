import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokens } from "../services/api";
import type { User } from "../services/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<User>;
  register: (data: { email: string; username: string; password: string; full_name: string; department_id?: number | null; job_title?: string }) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  isStaff: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

interface TokenResponse { access_token: string; refresh_token: string; user: User }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!tokens.access) { setUser(null); return; }
    try { setUser(await api.get<User>("/auth/me")); } catch { setUser(null); }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const login = useCallback(async (username: string, password: string) => {
    const r = await api.post<TokenResponse>("/auth/login", { username, password });
    tokens.set(r.access_token, r.refresh_token);
    setUser(r.user);
    return r.user;
  }, []);

  const register = useCallback(async (data: Parameters<AuthState["register"]>[0]) => {
    const r = await api.post<TokenResponse>("/auth/register", data);
    tokens.set(r.access_token, r.refresh_token);
    setUser(r.user);
    return r.user;
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch { /* token may already be invalid */ }
    tokens.clear();
    setUser(null);
  }, []);

  const value = useMemo(() => ({
    user, loading, login, register, logout, refreshUser,
    isStaff: user?.role === "it_support" || user?.role === "admin",
  }), [user, loading, login, register, logout, refreshUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
