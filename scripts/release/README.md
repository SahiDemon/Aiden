# Release and executable builds

Run these from the repository root after completing [setup](../../docs/setup.md):

```powershell
# Backend, dashboard, and Electron installer
.\scripts\release\build_release.ps1

# Optional installer version override
.\scripts\release\build_release.ps1 -Version 1.0.1

# Personal backend executable, without an Electron installer
.\scripts\release\build_exe.ps1
```

`build_installer.ps1` is a convenience entry point for the coordinated release workflow. Scripts resolve the repository location from their own path, so they can also be invoked from another working directory.

PyInstaller definitions live in [`packaging/`](../../packaging/README.md). Backend output remains in `dist/Aiden`; Electron installer output remains in `overlay/dist`. Generated output is ignored by Git.

The release workflow copies the blank `.env.example` template into the backend. The personal `build_exe.ps1` workflow can copy your private `.env`; do not redistribute that output without sanitizing it. See [security](../../SECURITY.md).
