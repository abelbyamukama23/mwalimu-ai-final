"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { login as apiLogin, logout as apiLogout, me as apiMe, type User } from "@/lib/api/auth";
import { singleFlightRefresh } from "@/lib/auth/refresh";
import {
  clearTokens,
  getAccess,
  getAccessRemainingMs,
  setAccess,
  setAuthExpiredHandler,
  setRefreshToken,
  setTokenChangeHandler,
} from "@/lib/auth/token-store";


type AuthStatus = "loading" | "authenticated" | "unauthenticated";

type AuthContextValue = {
  user: User | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  setSession: (access: string, user?: User | null) => Promise<void>;
  refreshSession: () => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Resume a session ~20s before the access token expires. */
const PROACTIVE_REFRESH_LEAD_MS = 20_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleRef = useRef<() => void>(() => {});

  const scheduleProactiveRefresh = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    const access = getAccess();
    if (!access) return;
    const remaining = getAccessRemainingMs(access);
    const delay = Math.max(remaining - PROACTIVE_REFRESH_LEAD_MS, 1_000);
    refreshTimer.current = setTimeout(async () => {
      const refreshed = await singleFlightRefresh();
      if (refreshed) scheduleRef.current();
    }, delay);
  }, []);

  useEffect(() => {
    scheduleRef.current = scheduleProactiveRefresh;
  }, [scheduleProactiveRefresh]);

  const logout = useCallback(() => {
    // Best-effort: the refresh token is cleared server-side via the cookie.
    void apiLogout().catch(() => undefined);
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    clearTokens();
    setUser(null);
    setStatus("unauthenticated");
    router.replace("/login");
  }, [router]);

  const setSession = useCallback(
    async (accessToken: string, initialUser?: User | null) => {
      setAccess(accessToken);
      setStatus("authenticated");
      if (initialUser) {
        setUser(initialUser);
      } else {
        try {
          setUser(await apiMe());
        } catch {
          setUser(null);
        }
      }
      scheduleProactiveRefresh();
    },
    [scheduleProactiveRefresh],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await apiLogin(email, password);
      if (result.refresh) {
        setRefreshToken(result.refresh);
      }
      await setSession(result.access, result.user ?? null);
    },
    [setSession],
  );

  const refreshSession = useCallback(async () => {
    const access = getAccess();
    if (access) {
      try {
        const currentUser = await apiMe();
        setUser(currentUser);
        setStatus("authenticated");
        scheduleProactiveRefresh();
        return;
      } catch {}
    }
    const refreshed = await singleFlightRefresh();
    if (refreshed) {
      try {
        const currentUser = await apiMe();
        setUser(currentUser);
        setStatus("authenticated");
        scheduleProactiveRefresh();
        return;
      } catch {}
    }
    clearTokens();
    setUser(null);
    setStatus("unauthenticated");
  }, [scheduleProactiveRefresh]);

  useEffect(() => {
    let cancelled = false;

    setAuthExpiredHandler(() => {
      if (cancelled) return;
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
      setUser(null);
      setStatus("unauthenticated");
    });

    setTokenChangeHandler((token) => {
      if (cancelled) return;
      if (token) {
        setStatus("authenticated");
        void apiMe()
          .then((u) => {
            if (!cancelled) setUser(u);
          })
          .catch(() => undefined);
        scheduleProactiveRefresh();
      } else {
        setUser(null);
        setStatus("unauthenticated");
      }
    });

    const bootstrap = async () => {
      let access = getAccess();
      const remaining = access ? getAccessRemainingMs(access) : 0;
      const isExpired = !access || remaining <= 0;

      if (isExpired) {
        const refreshed = await singleFlightRefresh();
        if (refreshed) {
          access = refreshed;
        }
      }

      if (access) {
        try {
          const currentUser = await apiMe();
          if (cancelled) return;
          setUser(currentUser);
          setStatus("authenticated");
          scheduleProactiveRefresh();
          return;
        } catch {
          // If profile fetch failed with 401, attempt refresh once
          const refreshed = await singleFlightRefresh();
          if (refreshed) {
            try {
              const currentUser = await apiMe();
              if (cancelled) return;
              setUser(currentUser);
              setStatus("authenticated");
              scheduleProactiveRefresh();
              return;
            } catch {}
          }
        }
      }

      if (!cancelled) {
        clearTokens();
        setUser(null);
        setStatus("unauthenticated");
      }
    };

    void bootstrap();

    return () => {
      cancelled = true;
      setAuthExpiredHandler(null);
      setTokenChangeHandler(null);
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [scheduleProactiveRefresh]);

  const value = useMemo(
    () => ({ user, status, login, setSession, refreshSession, logout }),
    [user, status, login, setSession, refreshSession, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

