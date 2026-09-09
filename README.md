# rescene_app

ReScene — a Flutter desktop app (Windows-first) that combines YOLO
segmentation, GPT image editing, and a local Llama chat, backed by a single
local Python server.

## Architecture

```
Flutter app (lib/)
  ├─ IdeaPage        pick image -> /yolo_seg -> /makeGPT (segment + GPT background edit)
  ├─ LlamaPage       chat -> /submit_content -> Ollama
  └─ ProfilePage     settings placeholder

Local backend (lib/run/app_DB.py)  [Flask, 127.0.0.1:5000]
  ├─ POST /yolo_seg         YOLO segmentation -> transparent PNG + detections
  ├─ POST /makeGPT          OpenAI gpt-image-1 background editing
  ├─ POST /submit_content   proxies chat to Ollama (http://localhost:11434)
  ├─ GET  /health           health check
  ├─ GET  /model_info       YOLO model metadata
  └─ GET  /get_image/<f>    serves stored images from lib/run/data/images/

MySQL (optional)   request logs; images are stored on disk, paths in DB
```

All backend configuration is environment-driven — see `lib/run/env.example`.

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

## Testing & analysis

```
flutter analyze
flutter test
python -m py_compile lib/run/app_DB.py
```

### CI (manual step)

Autonomous tooling cannot write into `.github/workflows/`, so add this as
`.github/workflows/ci.yml`:

```yaml
name: CI
on: [push, pull_request]
jobs:
  flutter:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: subosito/flutter-action@v2
        with: { channel: stable, cache: true }
      - run: flutter pub get
      - run: flutter analyze --fatal-infos
      - run: flutter test
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
