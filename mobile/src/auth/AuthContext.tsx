import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { ApiService } from '@/api/client';
import { ApiConfig } from '@/config';
import type { JsonObject } from '@/json';
import { isAdmin as isAdminUser, tryUserFromJson, type User } from '@/models/user';

export const TOKEN_STORAGE_KEY = 'rescene_token';

/**
 * Persistence seam for the session token.
 *
 * The Flutter client called SharedPreferences directly; injecting the adapter
 * keeps `AuthProvider` unit-testable without a device or native module.
 */
export interface TokenStorage {
  read(): Promise<string | null>;
  write(token: string): Promise<void>;
  clear(): Promise<void>;
}

export function createAsyncStorageTokenStorage(): TokenStorage {
  return {
    read: () => AsyncStorage.getItem(TOKEN_STORAGE_KEY),
    write: (token) => AsyncStorage.setItem(TOKEN_STORAGE_KEY, token),
    clear: () => AsyncStorage.removeItem(TOKEN_STORAGE_KEY),
  };
}

export interface AuthContextValue {
  user: User | null;
  token: string | null;
  initializing: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  /** Resolves to an error message on failure, or null on success. */
  login(username: string, password: string): Promise<string | null>;
  /** Resolves to an error message on failure, or null on success. */
  register(username: string, password: string): Promise<string | null>;
  /** Re-reads the account (e.g. after a membership purchase). */
  refreshUser(): Promise<void>;
  logout(): Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error('useAuth must be used inside an <AuthProvider>');
  }
  return value;
}

interface Session {
  user: User | null;
  token: string | null;
}

/** Initial session. Never mutated — `setSession` always replaces the object. */
const EMPTY_SESSION: Session = { user: null, token: null };

export interface AuthProviderProps {
  children: ReactNode;
  api?: ApiService;
  storage?: TokenStorage;
}

/**
 * Holds the session state and drives the login gate.
 *
 * Port of the Dart `AuthController`: the same bootstrap/login/register/
 * refresh/logout surface and the same failure semantics (an error string is
 * returned rather than thrown, so screens can render it inline).
 */
export function AuthProvider({ children, api, storage }: AuthProviderProps) {
  const apiClient = useMemo(() => api ?? new ApiService(), [api]);
  const storageClient = useMemo(() => storage ?? createAsyncStorageTokenStorage(), [storage]);

  // React state drives rendering; the ref lets async callbacks read the latest
  // session without depending on a possibly stale render closure. Both start
  // from the same empty session constant so no ref is read during render.
  const sessionRef = useRef<Session>(EMPTY_SESSION);
  const [session, setSessionState] = useState<Session>(EMPTY_SESSION);
  const [initializing, setInitializing] = useState(true);

  const setSession = useCallback((next: Session) => {
    sessionRef.current = next;
    setSessionState(next);
  }, []);

  const clearStoredToken = useCallback(async () => {
    try {
      await storageClient.clear();
    } catch {
      // Storage unavailable — the in-memory session is already cleared.
    }
  }, [storageClient]);

  const applyAuth = useCallback(
    async (body: JsonObject | null) => {
      const nextToken = typeof body?.token === 'string' ? body.token : null;
      const nextUser = tryUserFromJson(body?.user);
      setSession({ user: nextUser, token: nextToken });
      if (nextToken !== null) {
        try {
          await storageClient.write(nextToken);
        } catch {
          // Storage unavailable — the session just won't survive a restart.
        }
      }
    },
    [setSession, storageClient],
  );

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      let saved: string | null = null;
      try {
        saved = await storageClient.read();
      } catch {
        saved = null; // storage unavailable — start unauthenticated
      }
      if (cancelled) return;

      if (saved !== null) {
        const result = await apiClient.get(ApiConfig.mePath, { token: saved });
        if (cancelled) return;
        const restoredUser = result.ok ? tryUserFromJson(result.body?.user) : null;
        if (restoredUser !== null) {
          setSession({ user: restoredUser, token: saved });
        } else {
          setSession({ user: null, token: null });
          await clearStoredToken();
        }
      }

      if (!cancelled) setInitializing(false);
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, [apiClient, storageClient, setSession, clearStoredToken]);

  const login = useCallback(
    async (username: string, password: string) => {
      const result = await apiClient.post(ApiConfig.loginPath, {
        body: { username, password },
      });
      if (!result.ok) {
        return result.error ?? `Login failed (HTTP ${result.status})`;
      }
      await applyAuth(result.body);
      return null;
    },
    [apiClient, applyAuth],
  );

  const register = useCallback(
    async (username: string, password: string) => {
      const result = await apiClient.post(ApiConfig.registerPath, {
        body: { username, password },
      });
      if (!result.ok) {
        return result.error ?? `Registration failed (HTTP ${result.status})`;
      }
      await applyAuth(result.body);
      return null;
    },
    [apiClient, applyAuth],
  );

  const refreshUser = useCallback(async () => {
    const current = sessionRef.current.token;
    if (current === null) return;
    const result = await apiClient.get(ApiConfig.mePath, { token: current });
    if (!result.ok) return;
    const refreshed = tryUserFromJson(result.body?.user);
    if (refreshed !== null) {
      setSession({ user: refreshed, token: current });
    }
  }, [apiClient, setSession]);

  const logout = useCallback(async () => {
    setSession({ user: null, token: null });
    await clearStoredToken();
  }, [setSession, clearStoredToken]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: session.user,
      token: session.token,
      initializing,
      isAuthenticated: session.token !== null && session.user !== null,
      isAdmin: isAdminUser(session.user),
      login,
      register,
      refreshUser,
      logout,
    }),
    [session, initializing, login, register, refreshUser, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
