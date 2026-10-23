# Scripts

Everyday setup and launch commands stay in the repository root: `install.ps1`, `run_aiden.ps1`, and `stop_aiden.ps1`.

| Folder | Purpose |
| --- | --- |
| [release/](release/README.md) | Build backend executables and Windows installers |
| [diagnostics/](diagnostics/README.md) | Opt-in debugging, recording, and hardware checks |
| [windows/](windows/README.md) | Double-click startup and manual Windows power helpers |

Run Python utilities from the repository root with the installed environment:

```powershell
.\.venv\Scripts\python.exe scripts/list_stt_devices.py
```

Standalone utilities in this folder cover microphone discovery, provider setup, cache maintenance, and wake-word investigation. Some diagnostics change playback or Windows state; read their documentation before running them.
