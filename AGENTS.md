# Repository Guidelines

## Project Structure & Module Organization
- `src/main.py` orchestrates the tray app, FastAPI server, and wake-word pipeline.
- `src/core/`, `src/ai/`, `src/speech/`, `src/execution/`, and `src/utils/` host conversational flow, Groq access, audio handling, command runners, and helpers.
- `src/api/` (REST/WebSocket), `src/tray/`, and `smart_home/` power the dashboard bridge, tray UX, and ESP32 automation. Keep UI code in `dashboard/` and builds in `dashboard/build/`.
- Assets live in `config/`, `sounds/`, `vosk_models/`, `logs/`, and `src/temp/`; keep binaries out of Python packages to simplify environments.

## Build, Test, and Development Commands
- `powershell -ExecutionPolicy Bypass -File .\install.ps1` — bootstraps the venv, dependencies, and Vosk model.
- `.\run_aiden.ps1 -Debug` — runs the assistant with a console for asyncio and wake-word logs.
- `.\run_aiden.ps1` — launches the tray experience once the dashboard build exists.
- `python -m pip install -r requirements.txt` (inside `venv`) — rerun after dependency edits.
- `cd dashboard && npm run dev` for live React work, `npm run build` for production assets, and `npm run test` for UI tests (`CI=1` on pipelines).

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indents, snake_case members, PascalCase classes, and type hints at module boundaries; log via `src.utils.logger.get_logger`.
- React dashboard: functional components, PascalCase in `dashboard/src/components`, Tailwind utilities, hooks in `dashboard/src/hooks`.
- Environment variables stay UPPER_SNAKE_CASE and must exist in `.env.example` and `src/utils/config.py` before use.

## Testing Guidelines
- For assistant flows, run `.\run_aiden.ps1 -Debug`, trigger Porcupine and Vosk wake words, and confirm websocket updates at `http://localhost:5000`.
- Backend unit tests sit beside the code they cover (e.g., `src/core/tests/test_assistant.py`), use `pytest`, and follow `test_<feature>_<condition>` naming.
- Dashboard edits require `npm run test` plus a quick manual check of wake-word status, system context, and ESP32 widgets.

## Commit & Pull Request Guidelines
- Follow the Conventional Commit pattern from `git log` (`feat:`, `refactor:`, etc.) with imperative summaries and scoped details.
- PRs include a summary, testing notes, linked issues, and screenshots for dashboard or tray changes. Call out config/schema updates and new secrets so reviewers can reproduce.

## Configuration & Security Tips
- Store secrets only in `.env`; never commit `.env`, caches, or model binaries—`.env.example` holds placeholders.
- New configuration knobs should validate through `src/utils/config.get_settings` and document fallback values before rollout.

## Media Integrations
- Spotify control lives in `src/media/spotify_client.py` and `src/media/media_router.py`; provide credentials via `SPOTIFY_*` env vars and use `media_control` commands with `target:"spotify"`.
- Browser playback control (YouTube / YouTube Music) is handled by `src/media/browser_media_controller.py`, which discovers Chromium windows and sends keystrokes—keep actions abstracted through the media router.
