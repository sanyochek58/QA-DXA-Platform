import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, setUnauthorizedHandler, tokenStore } from "../api/client";
import type { Role, User } from "../api/types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  loginWithToken: (token: string) => Promise<User>;
  logout: () => void;
  can: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
    enabled: !!tokenStore.get(),
    retry: false,
    staleTime: 60_000,
  });

  const logout = useCallback(() => {
    tokenStore.clear();
    qc.clear();
    navigate("/login", { replace: true });
  }, [qc, navigate]);

  useEffect(() => setUnauthorizedHandler(logout), [logout]);

  const login = useCallback(
    async (email: string, password: string) => {
      const body = new URLSearchParams({ username: email, password });
      const { access_token } = await api<{ access_token: string }>("/auth/login", { method: "POST", body });
      tokenStore.set(access_token);
      const user = await api<User>("/auth/me");
      qc.setQueryData(["me"], user);
      return user;
    },
    [qc],
  );

  const loginWithToken = useCallback(
    async (token: string) => {
      tokenStore.set(token);
      const user = await api<User>("/auth/me");
      qc.setQueryData(["me"], user);
      return user;
    },
    [qc],
  );

  const user = tokenStore.get() ? (me.data ?? null) : null;
  const value: AuthValue = {
    user,
    loading: !!tokenStore.get() && me.isPending,
    login,
    loginWithToken,
    logout,
    can: (...roles) => !!user && roles.includes(user.role),
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth вне AuthProvider");
  return ctx;
}

/** Стартовая страница зависит от роли: у каждого свой главный экран. */
export function homeFor(role: Role) {
  return role === "admin" ? "/dashboard" : role === "radiologist" ? "/queue" : "/upload";
}
