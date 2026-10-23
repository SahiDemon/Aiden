# Backend packaging

| Definition | Output |
| --- | --- |
| `Aiden.spec` | Tray backend without a console window |
| `AidenConsole.spec` | Backend with a console window |

Use the [release scripts](../scripts/release/README.md) for coordinated builds. For a direct console build from the repository root:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm packaging/AidenConsole.spec
```

Source, asset, and icon paths are resolved relative to the repository containing these definitions. Generated `build/` and `dist/` output stays local. Runtime models and optional vendor executables must be installed before building.
