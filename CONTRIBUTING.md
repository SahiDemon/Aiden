# Contributing to Aiden

Work from `main` in a short-lived branch, keep changes focused, and preserve the existing voice and desktop behavior. Start with [setup](docs/setup.md) and [architecture](docs/architecture.md).

## Development setup

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Dev -IncludeOverlay
```

Use the same environment selected by setup (`.venv`, or an existing `venv`). Keep secrets in `.env` and add configuration options to both `.env.example` and `src/utils/config.py` with documented defaults.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest

cd dashboard
$env:CI = 'true'
npm run test -- --watchAll=false
npm run build

cd ../overlay
npm run build:app
```

Run checks relevant to your change. Python tests live in `tests/` and beside modules under `src/`; manual diagnostics live in `scripts/diagnostics` and are excluded from collection. For voice changes, run `.\run_aiden.ps1 -Debug`, check the intended wake engine, microphone capture, follow-ups, playback restoration, and WebSocket state updates. For dashboard changes, check wake status, system context, ESP32 controls, and timers. Describe any hardware checks you could not perform.

## Code and design

Use Python snake_case, four-space indentation, type hints at module boundaries, and `src.utils.logger.get_logger`. Keep React components functional and place UI logic in the relevant dashboard/overlay tree. Follow [design principles](docs/design.md), favor clear action labels, and retain existing behavior when refactoring.

Avoid committing environments, model binaries, generated builds, audio captures, caches, logs, or vendor executables. Keep lockfiles and templates. Do not remove regression tests solely to make the suite smaller.

## Pull requests

Use Conventional Commit summaries (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`). Explain the problem, final behavior, and validation. Include screenshots for visual changes and document new configuration options. Merge completed work into `main` before deleting its branch or worktree; preserve uncommitted files first.
