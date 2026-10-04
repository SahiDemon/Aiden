# Aiden overlay

A transparent Electron window shows listening, thinking, and replying states with animated wave effects. It connects to the backend at `ws://localhost:5000/api/v1/ws` and launches with Aiden when its local build is available.

## Develop

Use Node.js 22.12+ and run the Python backend separately.

```powershell
cd overlay
npm ci
npm run dev
```

This starts Vite and Electron. Renderer changes reload through Vite; Electron changes require restarting the development process. Window geometry and click-through behavior live in `electron/main.ts`; status and reconnection logic live in `src/hooks/useWebSocket.ts`.

## Build for local use

```powershell
npm run build:app
```

This checks TypeScript, builds the Vite renderer into `dist`, and compiles Electron into `dist-electron`. It does not package an installer. Aiden’s source launcher uses these assets with the local Electron dependency. Both output directories are ignored by Git.

From the repository root, `install.ps1 -IncludeOverlay` installs and builds the same source workflow.

## Package an installer

`npm run build` runs `build:app` followed by Electron Builder. Packaging expects the PyInstaller backend at `../dist/Aiden`. For the coordinated release workflow, use `build_release.ps1` from the repository root. Release configuration is blank; configure credentials after installing.

`npm run package` packages existing compiled assets. Do not distribute output from the personal `build_exe.ps1` workflow without checking its copied `.env`. See [SECURITY.md](../SECURITY.md).

## Troubleshooting

- Missing window: compile with `build:app` and verify `node_modules/.bin/electron.cmd` exists.
- Missing state updates: verify Aiden is running on port 5000 and the `/api/v1/ws` connection succeeds.
- Type/build failures: use the documented Node baseline and reproduce dependencies with `npm ci`.
- The transparent window may not have standard controls; stop Aiden through its tray/stop workflow.

The overlay uses React 19, TypeScript, Framer Motion, Electron, and Vite. It is separate from the React 18 dashboard.
