import { ApiResult } from '@/api/client';
import { createApi, createFetchMock, jsonResponse, rawResponse } from '@/testing/helpers';

describe('ApiResult', () => {
  it('reports 2xx as ok and exposes the error field', () => {
    expect(new ApiResult(200, {}).ok).toBe(true);
    expect(new ApiResult(299, {}).ok).toBe(true);
    expect(new ApiResult(500, { error: 'boom' }).error).toBe('boom');
    expect(new ApiResult(500, { error: 42 }).error).toBeUndefined();
  });
});

describe('ApiService.get', () => {
  it('prefixes the base URL and omits the auth header without a token', async () => {
    const { fetchImpl, requests } = createFetchMock(() => jsonResponse(200, { ok: true }));
    const api = createApi(fetchImpl, 'http://backend.test');

    const result = await api.get('/auth/me');

    expect(result.status).toBe(200);
    expect(requests[0]?.url).toBe('http://backend.test/auth/me');
    expect(requests[0]?.init.method).toBe('GET');
    expect(requests[0]?.init.headers.Authorization).toBeUndefined();
    expect(requests[0]?.init.headers['Content-Type']).toBe('application/json');
  });

  it('sends the bearer token when one is supplied', async () => {
    const { fetchImpl, requests } = createFetchMock(() => jsonResponse(200, {}));
    const api = createApi(fetchImpl);

    await api.get('/auth/me', { token: 'tok-123' });

    expect(requests[0]?.init.headers.Authorization).toBe('Bearer tok-123');
  });

  it('maps a non-JSON body to a null body', async () => {
    const { fetchImpl } = createFetchMock(() => rawResponse(502, '<html>bad gateway</html>'));
    const api = createApi(fetchImpl);

    const result = await api.get('/health');

    expect(result.status).toBe(502);
    expect(result.body).toBeNull();
    expect(result.ok).toBe(false);
  });

  it('reports an aborted request as status 0 with a timeout error', async () => {
    const fetchImpl = (_url: string, init: { signal?: AbortSignal }) =>
      new Promise<never>((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => {
          const error = new Error('Aborted');
          error.name = 'AbortError';
          reject(error);
        });
      });
    const api = createApi(fetchImpl);

    const result = await api.get('/slow', { timeoutMs: 1 });

    expect(result.status).toBe(0);
    expect(result.ok).toBe(false);
    expect(result.error).toBe('Request timed out');
  });

  it('reports a transport failure as status 0 with the cause', async () => {
    const api = createApi(() => Promise.reject(new Error('Network request failed')));

    const result = await api.get('/auth/me');

    expect(result.status).toBe(0);
    expect(result.error).toBe('Cannot reach server (Network request failed)');
  });
});

describe('ApiService.post', () => {
  it('serializes the JSON body and method', async () => {
    const { fetchImpl, requests } = createFetchMock(() => jsonResponse(200, { success: true }));
    const api = createApi(fetchImpl);

    const result = await api.post('/auth/login', { body: { username: 'a', password: 'b' } });

    expect(result.body?.success).toBe(true);
    expect(requests[0]?.init.method).toBe('POST');
    expect(requests[0]?.init.body).toBe(JSON.stringify({ username: 'a', password: 'b' }));
  });

  it('sends no body when none is given', async () => {
    const { fetchImpl, requests } = createFetchMock(() => jsonResponse(200, {}));
    const api = createApi(fetchImpl);

    await api.post('/membership/purchase');

    expect(requests[0]?.init.body).toBeUndefined();
  });
});

describe('ApiService.postMultipart', () => {
  it('leaves Content-Type unset so the runtime sets the boundary', async () => {
    const { fetchImpl, requests } = createFetchMock(() => jsonResponse(200, { success: true }));
    const api = createApi(fetchImpl);
    const form = new FormData();
    form.append('image', 'stub');

    await api.postMultipart('/yolo_seg', form, { token: 'tok' });

    expect(requests[0]?.init.headers['Content-Type']).toBeUndefined();
    expect(requests[0]?.init.headers.Authorization).toBe('Bearer tok');
    expect(requests[0]?.init.body).toBe(form);
  });
});
