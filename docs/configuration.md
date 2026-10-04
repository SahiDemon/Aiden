# Configuration

The source of configuration is `.env` at the repository root, validated by [`src/utils/config.py`](../src/utils/config.py). Dashboard settings may apply runtime overrides and persist updates. `.env.example` documents available options; never place actual keys in the template.

## Required services

| Setting | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `groq`, `gemini`, or `ollama`; default template uses Groq |
| `GROQ_API_KEY` | Groq chat when selected, and voice transcription regardless of chat provider |
| `GEMINI_API_KEY` | Required when Gemini is selected; numbered key slots are also supported |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Local Ollama endpoint and provisioned model when Ollama is selected |
| `NEON_DATABASE_URL` | PostgreSQL persistence for conversations, preferences, and timers |
| `REDIS_URL` | Conversation context and caching |

Empty required connection strings cause validation errors. The database client is configured for TLS; the documented setup uses Neon. A local PostgreSQL installation needs compatible TLS configuration. Provider model names and quotas can change; select an available model from your provider account or the dashboard rather than assuming a fixed free quota.

## Microphone and activation

```powershell
.\.venv\Scripts\python.exe scripts/list_stt_devices.py
```

Set `SPEECH_STT_DEVICE_INDEX` to the desired input, or configure `SPEECH_INPUT_DEVICE_NAME` to select by name. Blank values use default device selection. If your environment is `venv`, adjust the command accordingly.

| Option | Requirements |
| --- | --- |
| Vosk (default template) | Both `SPEECH_USE_PORCUPINE` and `SPEECH_USE_OPENWAKEWORD` false; downloaded Vosk directory at `SPEECH_VOSK_MODEL_PATH` |
| Porcupine | `SPEECH_USE_PORCUPINE=true`, a valid access key, and a compatible Windows `.ppn` file |
| openWakeWord | `SPEECH_USE_OPENWAKEWORD=true`, Porcupine disabled, and a model matching the phrase you intend to use |

Built-in openWakeWord models do not automatically recognize a custom “Aiden” phrase. Use a compatible custom model and follow the [personalized guide](guides/wake-word/personalized-v2.md). VAD thresholds and energy settings need microphone-specific calibration. Diagnostic audio capture is disabled by default.

Default activation hotkey: `Ctrl+Shift+Space`. Toggle wake detection: `Ctrl+.`. Stop listening: `Ctrl+Shift+/`. The corresponding `.env` settings are `HOTKEY`, `TOGGLE_HOTKEY`, and `STOP_LISTENING_HOTKEY`.

## Optional integrations

| Integration | Enable/configure |
| --- | --- |
| Spotify | `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN`; playback capabilities depend on your account and active device |
| Jellyfin | `JELLYFIN_URL`, `JELLYFIN_API_KEY`; uses available controllable sessions for playback and listening ducking |
| ESP32 | `ESP32_ENABLED=true` and your own `ESP32_IP_ADDRESS`; disabled by default |
| UPS | `UPS_ENABLED=true` and the correct `UPS_INFO_LOG_PATH`; review [shutdown behavior](guides/ups-monitoring.md) first |
| Google TTS | `SPEECH_TTS_PROVIDER=google` and a local credentials file; see [Chirp guide](guides/google-chirp-tts.md) |
| Cloudflare Tunnel | `CLOUDFLARE_TUNNEL_TOKEN`; provision Access protection separately before remote use |

Keep `API_HOST=localhost` for local use and Cloudflare Tunnel. Binding to `0.0.0.0` exposes the backend to the network. The API can execute computer commands and does not independently enforce user authentication. See [SECURITY.md](../SECURITY.md).

`SETTINGS_ENCRYPTION_KEY` can supply a dedicated key for stored settings encryption. Keep this key private and backed up; changing it can prevent existing stored secrets from decrypting.
