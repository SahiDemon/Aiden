# Manual diagnostics

These scripts are opt-in developer tools, separate from the automated suite. Read the selected script before running it. Use the repository root as your working directory, with the installed Python environment.

```powershell
.\.venv\Scripts\python.exe scripts/diagnostics/steam_lookup.py "cyberpunk"
```

| Tool/workflow | Effect |
| --- | --- |
| `app_launch.py` | Standalone application index and interactive launcher; can open apps |
| `debug_wake_word.bat` | Double-click entry point for the advanced microphone debugger |
| `steam_lookup.py` | Finds Steam libraries and resolves game identifiers |
| `fuzzy_search.py` | Investigates app matching; launch options can open applications |
| `process_context.py` | Interactive process viewer with explicit process termination commands |
| `mute_browser_audio.py` | Mutes browser audio sessions when directly executed |
| `verify_media_direct.py`, `verify_spotify_*.py` | Starts/changes real playback using configured accounts |
| `verify_self_destruct.py` | Exercises spoken self-termination and exits its process |
| `test_idle*.py`, `test_idle*.ps1` | Exercises idle behavior; some lock Windows |
| Live wake/record/train/calibrate scripts | Access microphone/model assets; recording scripts can save audio |
| UPS scripts | Inspect/simulate power events; review whether they send real application events |

Do not run live microphone tools alongside Aiden. Personal model assets and recorded data remain local. Automated checks use `python -m pytest` from the root and collect regression tests in `tests/` and beside modules under `src/`.
