import { render } from '@testing-library/react-native';
import React, { type ReactElement, type ReactNode } from 'react';

import { type ApiService, ApiService as ApiServiceImpl, type HttpFetch, type HttpRequestInit, type HttpResponse } from '@/api/client';
import { AuthContext, type AuthContextValue, type TokenStorage } from '@/auth/AuthContext';
import { userFromJson, type User } from '@/models/user';

export interface RecordedRequest {
  url: string;
  init: HttpRequestInit;
}

export interface FetchMock {
  fetchImpl: HttpFetch;
  requests: RecordedRequest[];
}

/** Builds an `HttpFetch` that records every call and answers via `handler`. */
export function createFetchMock(
  handler: (url: string, init: HttpRequestInit, requests: RecordedRequest[]) => HttpResponse | Promise<HttpResponse>,
): FetchMock {
  const requests: RecordedRequest[] = [];
  const fetchImpl: HttpFetch = async (url, init) => {
    requests.push({ url, init });
    return handler(url, init, requests);
  };
  return { fetchImpl, requests };
}

export function jsonResponse(status: number, body: unknown): HttpResponse {
  return { status, text: async () => JSON.stringify(body) };
}

/** Response with a body that is not a JSON object, e.g. an HTML error page. */
export function rawResponse(status: number, text: string): HttpResponse {
  return { status, text: async () => text };
}

export function createApi(fetchImpl: HttpFetch, baseUrl = 'http://backend.test'): ApiService {
  return new ApiServiceImpl({ baseUrl, fetchImpl });
}

export interface UserJsonOptions {
  role?: string;
  tier?: string;
  active?: boolean;
}

export function userJson(id: number, username: string, options: UserJsonOptions = {}) {
  const { role = 'user', tier = 'free', active = false } = options;
  return {
    id,
    username,
    role,
    membership: {
      tier,
      expires_at: active ? '2027-01-01T00:00:00' : null,
      active,
    },
    created_at: '2026-09-09T10:00:00',
  };
}

export function userFixture(id = 1, username = 'tester', options: UserJsonOptions = {}): User {
  return userFromJson(userJson(id, username, options));
}

/** In-memory `TokenStorage` so session tests never touch native storage. */
export function createMemoryStorage(initial: string | null = null): TokenStorage & { value: string | null } {
  const state = { value: initial };
  return {
    get value() {
      return state.value;
    },
    set value(next: string | null) {
      state.value = next;
    },
    read: async () => state.value,
    write: async (token: string) => {
      state.value = token;
    },
    clear: async () => {
      state.value = null;
    },
  };
}

export function createAuthValue(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    user: null,
    token: null,
    initializing: false,
    isAuthenticated: false,
    isAdmin: false,
    login: async () => null,
    register: async () => null,
    refreshUser: async () => undefined,
    logout: async () => undefined,
    ...overrides,
  };
}

/**
 * Renders `ui` with a stubbed auth context.
 *
 * The value is computed once so that `login`/`logout` spies keep a stable
 * identity across re-renders. `render` is asynchronous in React Native Testing
 * Library 14, so callers must await this.
 */
export async function renderWithAuth(ui: ReactElement, overrides: Partial<AuthContextValue> = {}) {
  const value = createAuthValue(overrides);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
  const view = await render(ui, { wrapper });
  return { ...view, auth: value };
}
