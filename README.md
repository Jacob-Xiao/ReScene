# rescene_app

ReScene — a Flutter desktop app (Windows-first) that combines YOLO
segmentation, GPT image editing, and a local Llama chat, backed by a single
local Python server. Accounts, membership tiers and an admin console are
built in.

## Architecture

```
Flutter app (lib/)
  ├─ Login/Register   accounts (/auth/*), session persisted locally
  ├─ IdeaPage         pick image -> /yolo_seg -> /makeGPT (segment + GPT edit)
  ├─ LlamaPage        chat -> /submit_content -> Ollama
  ├─ MembershipPage   tiers, demo checkout, purchase history
  ├─ ProfilePage      account card, admin entry, logout
  └─ AdminPage        stats, user management, request logs (role=admin)

Local backend (lib/run/app_DB.py)  [waitress, 127.0.0.1:5000]
  ├─ POST /yolo_seg         YOLO segmentation -> transparent PNG + detections
  ├─ POST /makeGPT          OpenAI gpt-image-1 background editing
  ├─ POST /submit_content   proxies chat to Ollama (http://localhost:11434)
  ├─ POST /auth/register|login, GET /auth/me
  ├─ GET  /membership/tiers|me, POST /membership/purchase (demo checkout)
  ├─ GET  /admin/stats|users|logs, POST /admin/users/<id>
  ├─ GET  /health           health check
  ├─ GET  /model_info       YOLO model metadata
  └─ GET  /get_image/<f>    serves stored images from lib/run/data/images/

MySQL (optional)   request logs; images are stored on disk, paths in DB
```

All backend configuration is environment-driven — see `lib/run/env.example`.

### Accounts, membership, admin

- **The first registered account automatically becomes the admin.** Set a
  long random `AUTH_SECRET` in `.env` so sessions survive server restarts.
- Passwords are stored as salted PBKDF2-SHA256 (200k iterations); login
  tokens are HMAC-signed and expire after 7 days.
- Membership checkout is a **demo**: orders are recorded as paid instantly,
  no real payment gateway is called. Pro ¥29/30d, Studio ¥99/30d.
- The admin console (Profile → Admin console, admin role only) shows usage
  stats, lets you search users, change roles, set tiers and extend
  memberships by 30 days.

## Backend setup

1. Create a virtualenv and install dependencies:

   ```
   cd lib/run
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   pip install -r requirements.txt
   ```

2. Configure secrets:

   ```
   copy env.example .env
   ```

   Fill in `OPENAI_API_KEY` and the `DB_*` values (a dedicated MySQL user is
   preferable to root). The `.env` file is loaded from the `lib/run`
   directory automatically and is git-ignored.

3. Pull the chat model and start Ollama:

   ```
   ollama pull llama3
   ollama serve
   ```

4. Start the backend:

   ```
   python app_DB.py
   ```

   It listens on `http://127.0.0.1:5000` (override with `HOST`/`PORT`).

## Frontend setup

```
flutter pub get
flutter run -d windows
```

Backend URLs, the Llama model name, and request timeouts live in
`lib/const.dart` (`ApiConfig`).

## React Native (Expo) client

A second client lives in `mobile/` — an Expo (React Native) app that mirrors the
Flutter screens and talks to the same local backend. The Flutter app is kept
as-is; the two clients are independent and can be built side by side.

```
cd mobile
npm install
npx expo start          # then press w (web) / a (Android) / i (iOS)
```

Targets: **iOS, Android and web** (Expo SDK 57, expo-router file-based routing).

Backend URLs can be overridden — something the Flutter app cannot do, and a
requirement for a phone, which cannot reach the desktop's loopback address:

```
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:5000 npx expo start
```

> The backend still binds to `127.0.0.1` only and sends no CORS headers. To use
> the mobile client against a machine on the LAN you must expose it
> (`HOST=0.0.0.0`), and the web target additionally needs CORS headers.

### React Native layout

```
mobile/
  app/                      expo-router routes (file-based)
    _layout.tsx             AuthProvider + root Stack
    (auth)/                 login + register; redirects once authenticated
    (tabs)/                 Idea / Llama / Membership / Profile tab shell
    admin.tsx               admin console (stats, users, logs)
    llama-conversation.tsx  Ollama chat
  src/
    api/client.ts           ApiService (fetch; injectable for tests)
    auth/AuthContext.tsx    session state + token storage
    models/                 user / membership / llama payload mapping
    components/              buttons, banners, prompt field, tab bar
    screens/                screen implementations
    testing/helpers.tsx     fetch + auth test doubles
```

### React Native checks

```
cd mobile
npm run typecheck         # tsc --noEmit
npm run lint              # eslint (eslint-config-expo)
npm test                  # jest (jest-expo)
```

The migration intentionally changes one behaviour: the Llama chat used to keep a
failed user message in the transcript once any earlier reply existed; the React
Native client drops only the message whose request failed.

## Concurrency & deployment

The backend runs on the production WSGI server **waitress** (multi-threaded;
gunicorn is not available on Windows) and is built for concurrent clients:

- YOLO inference runs behind a bounded admission gate (`MAX_YOLO_CONCURRENCY`,
  default 1). The **wait queue is bounded too** (`YOLO_MAX_WAITERS`): beyond it
  the server answers 503 + `Retry-After` immediately instead of queueing image
  payloads until memory runs out. Admission happens *before* the image is
  decoded, so a waiting request holds only its compressed bytes
- Per-IP sliding-window rate limiting protects all endpoints; `/makeGPT` has a
  separate, stricter cap (`GPT_RATE_LIMIT_PER_MINUTE`) to guard the OpenAI
  quota. Idle client keys are swept, so the limiter cannot leak memory
- **Every outbound call has a deadline** (`OPENAI_TIMEOUT` /
  `OPENAI_MAX_RETRIES`, `OLLAMA_TIMEOUT`). Without one, a stalled upstream
  would pin worker threads until the pool was exhausted
- The Ollama proxy uses a **per-thread** `requests.Session` with a sized
  urllib3 pool (`HTTP_POOL_SIZE`): a shared Session is not thread-safe, and the
  default pool (10) is smaller than the waitress thread count
- MySQL pool exhaustion retries briefly, then answers 503 + `Retry-After`
  rather than 500 (`DB_ACQUIRE_RETRIES`, `DB_ACQUIRE_BACKOFF`)
- `GET /health` reports the configured ceilings **and live saturation** (queue
  depth, rejections, pool contention, uptime). `GET /ready` is a readiness
  probe kept separate from liveness, so a load balancer can stop routing to an
  instance whose model or database is unavailable
- Generated images are pruned on a timer (`IMAGE_RETENTION_DAYS`,
  `IMAGE_MAX_FILES`) so `data/images` cannot fill the disk
- CORS is **opt-in** via `CORS_ALLOW_ORIGINS`, needed only by the Expo web
  build. It is off by default: a LAN-exposed backend with an open policy would
  let any page on the network call it with the user's token
- MySQL pool size, server threads, and connection limits stay env-configurable
  (`DB_POOL_SIZE`, `SERVER_THREADS`, `CONNECTION_LIMIT`, `CHANNEL_TIMEOUT`)

### Scaling past one process

`MAX_YOLO_CONCURRENCY`, the rate limiters and the admission gate are all
**per process**. Running N instances behind a load balancer therefore permits
N× concurrent inference — divide `MAX_YOLO_CONCURRENCY` accordingly, or move
inference into its own service. The rate limiter is per instance too, so a
cluster-wide quota needs a shared store.

Full design doc: [docs/high-concurrency-plan.md](docs/high-concurrency-plan.md)
(in Chinese). Verification tooling:

```
python lib/run/test_concurrency.py      # limiter / gate / counters / retry (stdlib only)
python lib/run/test_scaling.py          # retention, env contract, hardening wiring
python lib/run/load_test.py 64          # concurrent /health smoke test vs a running server
```

## Testing & analysis

Every stack has a local gate; run all three before pushing.

```
# Backend — stdlib only, needs no model, database or network
python lib/run/test_concurrency.py
python lib/run/test_scaling.py
python lib/run/test_auth.py
python -m py_compile lib/run/app_DB.py

# Flutter client
flutter analyze
flutter test

# React Native client (mobile/)
npm run typecheck && npm run lint && npm test
```

### CI (must be added by hand)

`.github/workflows/` is a protected path for the autonomous tooling that
maintains this repo, so the workflow below has to be created manually as
`.github/workflows/ci.yml`. Until that file exists the repository has **no
GitHub status checks** — the local commands above are the only gate.

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:
  workflow_dispatch:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  backend:
    name: Backend (python)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Compile backend modules
        run: >-
          python -m py_compile
          lib/run/app_DB.py
          lib/run/auth_utils.py
          lib/run/concurrency_utils.py
          lib/run/retention_utils.py
      - run: python lib/run/test_concurrency.py
      - run: python lib/run/test_scaling.py
      - run: python lib/run/test_auth.py

  flutter:
    name: Flutter client
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with:
          flutter-version: "3.44.0"
          channel: stable
          cache: true
      - run: flutter pub get
      - run: flutter analyze
      - run: flutter test

  mobile:
    name: React Native client
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: mobile
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: mobile/package-lock.json
      - run: npm ci
      - run: npm run typecheck
      - run: npm run lint
      - run: npm test
      - name: Bundle (web)
        run: npx expo export --platform web --output-dir dist
```

## Project layout

```
lib/
  main.dart                     app entry + named routes
  const.dart                    ApiConfig (URLs, model, timeouts) + theme
  components/bottom_nav_bar.dart
  models/
    idea_page/prompt_bar.dart   prompt input with live char counter
    llama_page/conversation_bar.dart
  pages/
    home_page.dart              IndexedStack tab shell (state survives tab switches)
    idea_page.dart              segment + GPT image flow
    llama_page.dart             chat entry list
    profile_page.dart
    sub_pages/llama_page_subpages/llama_conversation_page.dart
  run/
    app_DB.py                   the single backend server
    env.example                 template for .env
    requirements.txt            backend dependencies
    data/images/                generated images (git-ignored)
test/
  widget_test.dart              smoke + state-preservation + unit tests
```

## Notes

- The backend binds to `127.0.0.1` only and ships no CORS headers; only the
  desktop app on this machine can reach it.
- Generated images are written to `lib/run/data/images/`; the database only
  stores file paths.
- The Android platform folder was removed in this working tree; restore it
  with `flutter create --platforms android .` if needed.
