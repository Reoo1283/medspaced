"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  api,
  clearTokens,
  loginRequest,
  registerRequest,
  saveTokens,
} from "./api";
import type { Role, TokenPair, User } from "./types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
  canReview: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function applyPair(pair: TokenPair): User {
  saveTokens(pair);
  return pair.user;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("medspaced_access")
          : null;
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const me = await api<User>("/auth/me");
        if (!cancelled) setUser(me);
      } catch {
        clearTokens();
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const pair = await loginRequest(email, password);
    setUser(applyPair(pair));
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const pair = await registerRequest(email, password, fullName);
      setUser(applyPair(pair));
    },
    [],
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const role: Role | null = user?.role ?? null;

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        logout,
        canReview: role === "reviewer" || role === "admin",
        isAdmin: role === "admin",
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
