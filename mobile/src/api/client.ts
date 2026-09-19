import { ApiConfig } from '@/config';
import { isJsonObject, type JsonObject } from '@/json';

/**
 * Outcome of one API call: HTTP status plus decoded JSON body (when parseable).
 *
 * Port of the Dart `ApiResult`. Transport failures surface as status `0` with
 * an `error` message rather than a thrown exception, so callers branch on
 * `ok` exactly like the Flutter screens do.
 */
export class ApiResult {
  constructor(
    readonly status: number,
    readonly body: JsonObject | null,
  ) {}

  get ok(): boolean {
    return this.status >= 200 && this.status < 300;
  }

  get error(): string | undefined {
    const value = this.body?.error;
    return typeof value === 'string' ? value : undefined;
  }
}

/** Minimal response surface the client needs — keeps mocks trivial. */
export interface HttpResponse {
  status: number;
  text(): Promise<string>;
}

export interface HttpRequestInit {
  method: string;
  headers: Record<string, string>;
  body?: string | FormData;
  signal?: AbortSignal;
}

export type HttpFetch = (url: string, init: HttpRequestInit) => Promise<HttpResponse>;

const defaultFetch: HttpFetch = (url, init) => fetch(url, init);

export interface RequestOptions {
  /** Bearer token; pass `null`/`undefined` for unauthenticated calls. */
  token?: string | null;
  timeoutMs?: number;
}

export interface PostOptions extends RequestOptions {
  body?: JsonObject;
}

export interface ApiServiceOptions {
  baseUrl?: string;
  fetchImpl?: HttpFetch;
}

/**
 * Thin HTTP wrapper around the local backend.
 *
 * `fetchImpl` and `baseUrl` are injectable so screens and hooks can be unit
 * tested without a live server (the Dart client did the same with `http.Client`).
 */
export class ApiService {
  private readonly baseUrl: string;
  private readonly fetchImpl: HttpFetch;

  constructor(options: ApiServiceOptions = {}) {
    this.baseUrl = options.baseUrl ?? ApiConfig.baseUrl;
    this.fetchImpl = options.fetchImpl ?? defaultFetch;
  }

  async get(path: string, options: RequestOptions = {}): Promise<ApiResult> {
    return this.request('GET', path, {
      token: options.token,
      timeoutMs: options.timeoutMs,
    });
  }

  async post(path: string, options: PostOptions = {}): Promise<ApiResult> {
    return this.request('POST', path, {
      token: options.token,
      timeoutMs: options.timeoutMs,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  }

  /**
   * Multipart upload (`/yolo_seg`). The base64 endpoints (`/makeGPT`,
   * `/submit_content`) stay JSON; only image upload is multipart.
   */
  async postMultipart(
    path: string,
    form: FormData,
    options: RequestOptions = {},
  ): Promise<ApiResult> {
    return this.request('POST', path, {
      token: options.token,
      timeoutMs: options.timeoutMs,
      body: form,
      jsonContentType: false,
    });
  }

  private async request(
    method: string,
    path: string,
    options: {
      token?: string | null;
      timeoutMs?: number;
      body?: string | FormData;
      jsonContentType?: boolean;
    },
  ): Promise<ApiResult> {
    const timeoutMs = options.timeoutMs ?? ApiConfig.requestTimeoutMs;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method,
        headers: buildHeaders(options.token, options.jsonContentType ?? true),
        body: options.body,
        signal: controller.signal,
      });
      return new ApiResult(response.status, await readJsonBody(response));
    } catch (error) {
      if (isAbortError(error)) {
        return new ApiResult(0, { error: 'Request timed out' });
      }
      return new ApiResult(0, { error: `Cannot reach server (${describeError(error)})` });
    } finally {
      clearTimeout(timer);
    }
  }
}

function buildHeaders(token: string | null | undefined, jsonContentType: boolean): Record<string, string> {
  const headers: Record<string, string> = {};
  if (jsonContentType) headers['Content-Type'] = 'application/json';
  // The Dart client only skips the header for a null token, so an empty string
  // still sends one; keep that behaviour for parity with `/auth/me` probing.
  if (token != null) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function readJsonBody(response: HttpResponse): Promise<JsonObject | null> {
  try {
    const text = await response.text();
    if (!text) return null;
    const decoded: unknown = JSON.parse(text);
    return isJsonObject(decoded) ? decoded : null;
  } catch {
    // Non-JSON or truncated body — callers see a null body, like the Dart
    // `_decode` catching FormatException.
    return null;
  }
}

function isAbortError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && (error as { name?: unknown }).name === 'AbortError';
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
