import { act, renderHook, waitFor } from '@testing-library/react-native';
import React, { type ReactNode } from 'react';

import { AuthProvider, useAuth, type TokenStorage } from '@/auth/AuthContext';
import type { ApiService } from '@/api/client';
import { createApi, createFetchMock, createMemoryStorage, jsonResponse, userJson } from '@/testing/helpers';

function wrapperFor(api: ApiService, storage: TokenStorage) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <AuthProvider api={api} storage={storage}>
        {children}
      </AuthProvider>
    );
  };
}

/** Renders the auth hook and waits for bootstrap to settle. */
async function mountAuth(api: ApiService, storage: TokenStorage) {
  const view = await renderHook(() => useAuth(), { wrapper: wrapperFor(api, storage) });
  await waitFor(() => expect(view.result.current.initializing).toBe(false));
  return view;
}

describe('AuthProvider bootstrap', () => {
  it('restores a saved session and validates it against /auth/me', async () => {
    const { fetchImpl, requests } = createFetchMock(() =>
      jsonResponse(200, {
        success: true,
        user: userJson(1, 'tester', { tier: 'pro', active: true }),
      }),
    );
    const storage = createMemoryStorage('saved-token');

    const { result } = await mountAuth(createApi(fetchImpl), storage);

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('saved-token');
    expect(result.current.user?.username).toBe('tester');
    expect(result.current.user?.membershipTier).toBe('pro');

    expect(requests).toHaveLength(1);
    expect(requests[0]?.url).toBe('http://backend.test/auth/me');
    expect(requests[0]?.init.headers.Authorization).toBe('Bearer saved-token');
  });

  it('discards a token the server rejects and clears storage', async () => {
    const { fetchImpl } = createFetchMock(() => jsonResponse(401, { error: 'invalid token' }));
    const storage = createMemoryStorage('stale-token');

    const { result } = await mountAuth(createApi(fetchImpl), storage);

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
    expect(storage.value).toBeNull();
  });

  it('starts unauthenticated without a stored token and makes no request', async () => {
    const { fetchImpl, requests } = createFetchMock(() => jsonResponse(200, {}));
    const storage = createMemoryStorage(null);

    const { result } = await mountAuth(createApi(fetchImpl), storage);

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.initializing).toBe(false);
    expect(requests).toHaveLength(0);
  });

  it('starts unauthenticated when token storage is unavailable', async () => {
    const { fetchImpl } = createFetchMock(() => jsonResponse(200, {}));
    const storage: TokenStorage = {
      read: () => Promise.reject(new Error('storage offline')),
      write: () => Promise.reject(new Error('storage offline')),
      clear: () => Promise.reject(new Error('storage offline')),
    };

    const { result } = await mountAuth(createApi(fetchImpl), storage);

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.initializing).toBe(false);
  });
});

describe('AuthProvider login', () => {
  it('stores the token, sets the user and persists the session', async () => {
    const { fetchImpl, requests } = createFetchMock(() =>
      jsonResponse(200, { success: true, token: 'tok-123', user: userJson(1, 'tester') }),
    );
    const storage = createMemoryStorage(null);
    const { result } = await mountAuth(createApi(fetchImpl), storage);

    let error: string | null = 'unset';
    await act(async () => {
      error = await result.current.login('tester', 'password123');
    });

    expect(error).toBeNull();
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('tok-123');
    expect(result.current.user?.username).toBe('tester');
    expect(storage.value).toBe('tok-123');

    expect(requests[0]?.url).toBe('http://backend.test/auth/login');
    expect(requests[0]?.init.body).toBe(
      JSON.stringify({ username: 'tester', password: 'password123' }),
    );
    expect(requests[0]?.init.headers.Authorization).toBeUndefined();
  });

  it('returns the server message and stays unauthenticated on failure', async () => {
    const { fetchImpl } = createFetchMock(() =>
      jsonResponse(401, { success: false, error: 'Incorrect username or password' }),
    );
    const storage = createMemoryStorage(null);
    const { result } = await mountAuth(createApi(fetchImpl), storage);

    let error: string | null = null;
    await act(async () => {
      error = await result.current.login('tester', 'wrongpass');
    });

    expect(error).toBe('Incorrect username or password');
    expect(result.current.isAuthenticated).toBe(false);
    expect(storage.value).toBeNull();
  });

  it('falls back to a status message when the server sends no error field', async () => {
    const { fetchImpl } = createFetchMock(() => jsonResponse(500, {}));
    const { result } = await mountAuth(createApi(fetchImpl), createMemoryStorage(null));

    let error: string | null = null;
    await act(async () => {
      error = await result.current.login('tester', 'pw');
    });

    expect(error).toBe('Login failed (HTTP 500)');
  });

  it('reports a transport failure without throwing', async () => {
    const { result } = await mountAuth(
      createApi(() => Promise.reject(new Error('Network request failed'))),
      createMemoryStorage(null),
    );

    let error: string | null = null;
    await act(async () => {
      error = await result.current.login('tester', 'pw');
    });

    expect(error).toBe('Cannot reach server (Network request failed)');
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('exposes isAdmin for admin accounts', async () => {
    const { fetchImpl } = createFetchMock(() =>
      jsonResponse(200, {
        success: true,
        token: 'tok',
        user: userJson(1, 'root', { role: 'admin' }),
      }),
    );
    const { result } = await mountAuth(createApi(fetchImpl), createMemoryStorage(null));

    await act(async () => {
      await result.current.login('root', 'password123');
    });

    expect(result.current.isAdmin).toBe(true);
  });
});

describe('AuthProvider register', () => {
  it('authenticates the new account', async () => {
    const { fetchImpl, requests } = createFetchMock(() =>
      jsonResponse(200, { success: true, token: 'tok-new', user: userJson(2, 'newbie') }),
    );
    const storage = createMemoryStorage(null);
    const { result } = await mountAuth(createApi(fetchImpl), storage);

    let error: string | null = null;
    await act(async () => {
      error = await result.current.register('newbie', 'password123');
    });

    expect(error).toBeNull();
    expect(result.current.isAuthenticated).toBe(true);
    expect(requests[0]?.url).toBe('http://backend.test/auth/register');
    expect(storage.value).toBe('tok-new');
  });

  it('uses the registration-specific failure message', async () => {
    const { fetchImpl } = createFetchMock(() => jsonResponse(409, {}));
    const { result } = await mountAuth(createApi(fetchImpl), createMemoryStorage(null));

    let error: string | null = null;
    await act(async () => {
      error = await result.current.register('newbie', 'password123');
    });

    expect(error).toBe('Registration failed (HTTP 409)');
  });
});

describe('AuthProvider refresh and logout', () => {
  it('re-reads the account after a membership change', async () => {
    const { fetchImpl } = createFetchMock((url) => {
      if (url.endsWith('/auth/login')) {
        return jsonResponse(200, {
          success: true,
          token: 'tok',
          user: userJson(1, 'tester', { tier: 'free' }),
        });
      }
      return jsonResponse(200, {
        success: true,
        user: userJson(1, 'tester', { tier: 'pro', active: true }),
      });
    });
    const { result } = await mountAuth(createApi(fetchImpl), createMemoryStorage(null));

    await act(async () => {
      await result.current.login('tester', 'password123');
    });
    expect(result.current.user?.membershipTier).toBe('free');

    await act(async () => {
      await result.current.refreshUser();
    });

    expect(result.current.user?.membershipTier).toBe('pro');
    expect(result.current.user?.membershipActive).toBe(true);
  });

  it('refreshing without a session is a no-op', async () => {
    const { fetchImpl, requests } = createFetchMock(() => jsonResponse(200, {}));
    const { result } = await mountAuth(createApi(fetchImpl), createMemoryStorage(null));

    await act(async () => {
      await result.current.refreshUser();
    });

    expect(requests).toHaveLength(0);
  });

  it('logout clears the session and the stored token', async () => {
    const { fetchImpl } = createFetchMock(() =>
      jsonResponse(200, { success: true, token: 'tok', user: userJson(1, 'tester') }),
    );
    const storage = createMemoryStorage(null);
    const { result } = await mountAuth(createApi(fetchImpl), storage);

    await act(async () => {
      await result.current.login('tester', 'password123');
    });
    expect(result.current.isAuthenticated).toBe(true);
    expect(storage.value).toBe('tok');

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(storage.value).toBeNull();
  });
});
