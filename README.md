<div align="center">

# Aiden

**Your Windows assistant, a voice command away.**

Open applications, manage media, schedule actions, and control your smart home from a local dashboard and desktop overlay.

[Get started](docs/setup.md) · [Configuration](docs/configuration.md) · [Contribute](CONTRIBUTING.md) · [Troubleshooting](docs/troubleshooting.md)

![Platform: Windows](https://img.shields.io/badge/platform-Windows-2563eb)
![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776ab)
![Interface: React](https://img.shields.io/badge/interface-React-61dafb)

</div>

---

## What you can do

| Capability | Examples |
| --- | --- |
| Voice and conversation | Say “Aiden”, use `Ctrl+Shift+Space`, or type in the dashboard. Follow up within the same conversation. |
| Applications and Windows | Open installed apps and Steam games; lock, sleep, restart, or shut down; adjust supported display and audio controls. |
| Timers and delayed actions | Schedule commands and view or cancel pending actions in the dashboard. |
| Media | Control Spotify, YouTube, YouTube Music, and Jellyfin; pause supported playback while listening and restore it afterward. |
| Smart home | Control configured ESP32 devices and view their state. Optional; disabled in a fresh setup. |
| Desktop presence | A system tray app, live React dashboard, and optional animated Electron overlay. |

Wake-word recognition runs locally using Vosk, Porcupine, or openWakeWord. Spoken-command transcription uses Groq; Edge TTS and cloud LLM providers also need internet access. Ollama is available for local LLM responses. See [data flow and security](SECURITY.md) before enabling remote access.

## Start on Windows

Install **Python 3.10+** (3.11 recommended), **Node.js 22.12+**, and Git. Enable Python on PATH and reopen PowerShell after installing prerequisites.

```powershell
git clone https://github.com/SahiDemon/Aiden.git
cd Aiden
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer creates or reuses a Python environment, installs dependencies, downloads the English Vosk model, creates `.env` if needed, and builds the dashboard. It preserves an existing `.env`.

Edit `.env` before your first launch:

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=your-key
NEON_DATABASE_URL=your-postgresql-connection-string
REDIS_URL=your-redis-connection-string
```

These services are required by the current configuration validation. Use your own credentials; never commit them. Other LLM providers and optional integrations are explained in [configuration](docs/configuration.md).

```powershell
.\run_aiden.ps1 -Debug
```

Open **[localhost:5000](http://localhost:5000)**. Try a harmless request such as “What time is it?” or “Open Notepad”. Once setup works, use `.\run_aiden.ps1` for the background tray experience.

For the desktop overlay, install with `-IncludeOverlay`. For tests and developer tools, add `-Dev`. [Full setup guide →](docs/setup.md)

## Find your way around

```text
Aiden/
├── src/                 Python assistant, API, speech, media, and tray
├── dashboard/           React dashboard served by the backend
├── overlay/             Electron + React desktop overlay
├── config/              Shared prompts and configuration assets
├── tests/               Automated regression tests
├── scripts/             Utilities and opt-in diagnostics
├── tools/               Optional tool helpers; vendor executables stay local
└── docs/                Setup, architecture, and integration guides
```

Models, environments, logs, caches, vendor executables, and build output are generated or machine-specific and ignored by Git. `install.ps1` restores the default Vosk model and dashboard build for new clones. Optional vendor tools must be installed separately.

## Develop and verify

```powershell
# From the repository root
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest

# Dashboard
cd dashboard
npm ci
npm run dev
```

If setup reused `venv`, substitute `venv` for `.venv` in Python commands. Dashboard tests use `npm run test -- --watchAll=false`; production assets use `npm run build`. The overlay has a separate [development guide](overlay/README.md).

Keep hardware diagnostics outside the automated suite. Some diagnostics change playback, mute applications, lock Windows, or terminate their own process; run only the specific script you intend to use. [Contribution guide →](CONTRIBUTING.md)

## Learn more

- [Documentation index](docs/README.md) — onboarding and integrations
- [Architecture](docs/architecture.md) — request flow and module boundaries
- [Design principles](docs/design.md) — the dashboard’s visual direction
- [Security](SECURITY.md) — local API, credentials, and Cloudflare Access
- [Changelog](CHANGELOG.md) — project history

Response time and recognition accuracy depend on your microphone, environment, model, and network. No fixed latency or perfect detection guarantee is assumed.
