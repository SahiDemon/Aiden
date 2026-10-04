# Troubleshooting

Start with `.\run_aiden.ps1 -Debug` and inspect `logs/`. Share only redacted errors; logs may contain commands, transcript text, system information, or connection details.

| Problem | What to check |
| --- | --- |
| Python/npm not found | Install prerequisites with PATH enabled, reopen PowerShell, and run `install.ps1 -CheckOnly`. |
| Dependency installation fails | Read the first failing package/error. Audio wheels depend on Python version; try a supported Python 3.11 environment. Avoid installing into system Python accidentally. |
| Required setting validation fails | Fill the selected provider key, `NEON_DATABASE_URL`, and `REDIS_URL` in the root `.env`. Groq is needed for voice transcription. |
| PostgreSQL/Redis cannot connect | Check credentials, hostname, TLS requirements, firewall, and provider availability. Setup completion does not verify these services. |
| Dashboard missing or stale | Run `npm ci` then `npm run build` in `dashboard`; restart Aiden when needed. The dev server is separate from the backend’s production dashboard. |
| “Aiden is already running” | Use the existing tray instance or intentionally stop it before starting another. Do not run competing microphone listeners. |
| Microphone not detected | Enable Windows microphone access; run `scripts/list_stt_devices.py`, then set your input index/name. Remove an old USB device name when changing hardware. |
| Wake phrase misses or false triggers | Check the selected engine, model phrase, model path, background audio, energy/VAD thresholds, and debounce. Use the wake-word guides for controlled tuning. |
| Vosk model missing | Rerun setup without `-SkipModel`, or download/extract the English model to the path in `.env`. Custom models remain your responsibility. |
| Overlay does not appear | In `overlay`, run `npm ci` and `npm run build:app`; verify the backend is listening and `/api/v1/ws` connects. |
| Spotify/Jellyfin does not resume | Confirm credentials and a controllable playback session. Disappearing or unsupported sessions cannot be resumed; inspect media logs. |
| ESP32/UPS warnings on a new machine | Leave those integrations disabled until their addresses/log paths are configured. |
| Cloudflare says no MFA methods | Cloudflare account MFA and Access application MFA have separate enrollment. Configure the Access App Launcher and enroll Access MFA for the relevant identity. |

## Safe diagnostic workflow

Use the automated suite first: `.\.venv\Scripts\python.exe -m pytest`. It collects only `tests/test_*.py`. Manual diagnostics live in `scripts/diagnostics`; read their [guide](../scripts/diagnostics/README.md) before running a script.

Do not run live wake-word tools alongside Aiden; both may compete for the microphone. Some recording tools save audio locally when explicitly enabled. Do not commit recordings, trained personal models, credentials, or generated output.
