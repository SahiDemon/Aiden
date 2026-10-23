# Windows helpers

| File | Purpose |
| --- | --- |
| `start.bat` | Optional double-click launcher for the root `run_aiden.ps1`; retains its administrator prompt |
| `apply_overrides.ps1` | Manual sleep/power request overrides for specific drivers and applications; requires administrator access |

Normal setup and launch use `install.ps1` and `run_aiden.ps1` in the repository root. The power overrides are machine-specific and are never applied by installation or normal startup. Read the script before choosing to run it.
