import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { apiFetch } from "@/api/client";
import {
  clearStoredAuth,
  readStoredAuth,
  storeAuth,
  type AuthenticatedUser,
} from "@/services/auth";

type AuthStatus = "anonymous" | "authenticated";
type AuthProviderKind = "demo" | "external" | null;

type AuthContextValue = {
  status: AuthStatus;
  provider: AuthProviderKind;
  token: string | null;
  user: AuthenticatedUser | null;
  loginWithPassword: (email: string, password: string) => Promise<void>;
  loginWithToken: (token: string) => Promise<void>;
  logout: () => void;
};

type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  user: AuthenticatedUser;
};

type AuthConfigResponse = {
  provider: "demo" | "external";
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const initialAuth = readStoredAuth();
  const [token, setToken] = useState<string | null>(initialAuth?.token ?? null);
  const [user, setUser] = useState<AuthenticatedUser | null>(initialAuth?.user ?? null);
  const [provider, setProvider] = useState<AuthProviderKind>(null);

  useEffect(() => {
    apiFetch<AuthConfigResponse>("/api/auth/config")
      .then((config) => setProvider(config.provider))
      .catch(() => setProvider("demo"));
  }, []);

  const loginWithPassword = useCallback(async (email: string, password: string) => {
    const response = await apiFetch<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });

    storeAuth(response.access_token, response.user);
    setToken(response.access_token);
    setUser(response.user);
  }, []);

  const loginWithToken = useCallback(async (accessToken: string) => {
    const authenticatedUser = await apiFetch<AuthenticatedUser>("/api/auth/me", {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    storeAuth(accessToken, authenticatedUser);
    setToken(accessToken);
    setUser(authenticatedUser);
  }, []);

  const logout = useCallback(() => {
    clearStoredAuth();
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status: token && user ? "authenticated" : "anonymous",
      provider,
      token,
      user,
      loginWithPassword,
      loginWithToken,
      logout,
    }),
    [loginWithPassword, loginWithToken, logout, provider, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
