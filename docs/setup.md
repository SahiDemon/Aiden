# Windows setup

## Prerequisites

- Windows with a working microphone and audio output.
- Python 3.10 or newer on PATH; Python 3.11 is a conservative starting point for audio dependencies.
- Node.js 22.12 or newer and npm on PATH.
- Git and access to this repository.
- A Groq key, a Neon PostgreSQL connection string, and a Redis connection string. Configuration validation currently requires PostgreSQL and Redis even if you select a different LLM.

Groq also transcribes recorded commands. Selecting Gemini or Ollama for chat does not replace that voice transcription dependency.

## Install

```powershell
git clone https://github.com/SahiDemon/Aiden.git
cd Aiden
powershell -ExecutionPolicy Bypass -File .\install.ps1 -CheckOnly
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

`-CheckOnly` checks Python, Node, and npm without installing packages or changing configuration. The full installer:

1. Reuses `.venv`, or an existing `venv`; otherwise creates `.venv`.
2. Installs Python runtime dependencies through that environment’s interpreter.
3. Copies `.env.example` to `.env` only when `.env` does not exist.
4. Downloads and extracts `vosk-model-small-en-us-0.15` if its model file is missing.
5. Runs `npm ci` and `npm run build` in `dashboard`.

Allow time and disk space for audio/ML dependencies, including PyTorch. A failed step stops setup and reports its error. Fix the cause and rerun the same command.

| Switch | Purpose |
| --- | --- |
| `-Dev` | Include pytest and development tools |
| `-IncludeOverlay` | Install and compile the optional desktop overlay without packaging an installer |
| `-SkipModel` | Use an already provisioned/custom wake-word model; configure its path yourself |
| `-SkipDashboard` | Skip Node/dashboard installation for backend-only development; the standard launcher still needs a dashboard build |
| `-CheckOnly` | Check prerequisites with no installation changes |

## Configure

Edit `.env` in a local editor. Populate `GROQ_API_KEY`, `NEON_DATABASE_URL`, and `REDIS_URL`. The shipped template selects Groq for chat, keeps the API on `localhost`, uses the default microphone, and disables ESP32, UPS, and keyed Porcupine detection until configured.

To use Gemini, set `LLM_PROVIDER=gemini` and a Gemini key. To use Ollama, install/run Ollama, provision the selected model, and set `LLM_PROVIDER=ollama`. Retain the Groq key for voice transcription. See [configuration](configuration.md).

Database tables are created when the app connects at startup. The installer does not connect to your database or verify credentials. Do not treat a successful dependency installation as a successful service connection.

## First launch

```powershell
.\run_aiden.ps1 -Debug
```

Open [the local dashboard](http://localhost:5000). Check the console for database, Redis, and microphone connection errors. Start with “What time is it?” or “Open Notepad”, then confirm voice status and dashboard updates. For normal tray use, run `.\run_aiden.ps1`. Use the tray’s Exit action or `.\stop_aiden.ps1` when intentionally stopping the app.

The optional overlay starts automatically when its compiled assets and Electron dependencies are present. To add it later:

```powershell
cd overlay
npm ci
npm run build:app
```

## Update an existing installation

Commit or save your development work before pulling updates. Stop Aiden before replacing runtime dependencies.

```powershell
git switch main
git pull --ff-only
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

An existing `.env` is preserved. Compare newly documented options with `.env.example` rather than replacing your credentials. Rebuild the overlay if you use it. Models, dependencies, caches, and builds stay local and are intentionally absent from Git.

## Optional Windows tools

NirCmd supports additional audio/display actions; ClickMonitorDDC supports compatible external monitor brightness. Acquire them from their publishers and place executables in the `tools` locations documented in [tools/README.md](../tools/README.md). Neither is required for conversation or application launching.

## Packaged releases

`build_release.ps1` builds the dashboard, PyInstaller backend, and Electron installer. Release output contains the blank `.env.example` template as `.env`, including when reusing an existing backend build. Configure credentials after installation. `build_exe.ps1` is a personal/local executable workflow that can copy your `.env`; do not redistribute that output. See [security](../SECURITY.md).
