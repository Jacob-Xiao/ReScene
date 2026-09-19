/**
 * Configuration for the ReScene backend (`lib/run/app_DB.py`).
 *
 * TypeScript port of `lib/const.dart` (`ApiConfig`) from the Flutter client.
 *
 * The Flutter app hardcodes `http://127.0.0.1:5000`, which only works when the
 * client runs on the same machine as the server. A phone cannot reach the
 * desktop's loopback interface, so the base URL is overridable — point it at
 * the machine running the backend before starting Expo:
 *
 *   EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:5000 npx expo start
 */
const DEFAULT_BASE_URL = 'http://127.0.0.1:5000';

function normalizeBaseUrl(raw: string | undefined): string {
  const value = raw?.trim();
  if (!value) return DEFAULT_BASE_URL;
  return value.replace(/\/+$/, '');
}

export const baseUrl = normalizeBaseUrl(process.env.EXPO_PUBLIC_API_BASE_URL);

export const ApiConfig = {
  baseUrl,

  // Auth.
  loginPath: '/auth/login',
  registerPath: '/auth/register',
  mePath: '/auth/me',

  // Membership.
  tiersPath: '/membership/tiers',
  purchasePath: '/membership/purchase',
  membershipMePath: '/membership/me',

  // Admin.
  adminStatsPath: '/admin/stats',
  adminUsersPath: '/admin/users',
  adminLogsPath: '/admin/logs',

  // Inference.
  yoloSegPath: '/yolo_seg',
  makeGptPath: '/makeGPT',
  submitContentPath: '/submit_content',

  /** Model name sent to Ollama; keep in sync with `ollama pull`. */
  llamaModel: 'llama3',

  /** GPT image generation can take a while; YOLO/Ollama are faster. */
  requestTimeoutMs: 120_000,
  gptTimeoutMs: 300_000,
} as const;
