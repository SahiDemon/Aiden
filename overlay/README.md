# Aiden overlay

A transparent Electron window shows listening, thinking, and replying states with animated wave effects. It connects to the backend at `ws://localhost:5000/api/v1/ws` and launches with Aiden when its local build is available.

The overlay covers the primary monitor's full bounds, including its corners. A transparent edge glow surrounds the desktop, with a compact voice capsule at the top. Listening uses blue/cyan, thinking uses indigo, and speaking uses cyan/teal. The window remains non-focusable and passes clicks through. Display/DPI changes refit its bounds. Only active voice sessions show the glow; typed chat remains silent and does not activate it. Motion uses opacity and transform, with a static reduced-motion alternative.

For a safe browser preview, run `npm run dev:vite` and open `http://localhost:5173/?preview`. The development-only controls switch visual states without sending assistant commands. Production builds exclude this preview.

`npm run test` verifies the voice lifecycle with simulated WebSocket and Electron IPC events: listening → capture handoff → thinking → speaking → idle, cancellation, fresh-turn text clearing, silent text chat, disconnect/reconnect, and cleanup. Capture-end idle stays in Thinking until the reply is ready; playback-end idle clears and hides the overlay. An explicit `active:false` always ends the session.

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

`npm run build` runs `build:app` followed by Electron Builder. Packaging expects the PyInstaller backend at `../dist/Aiden`. For the coordinated release workflow, use `scripts/release/build_release.ps1` from the repository root. Release configuration is blank; configure credentials after installing.

`npm run package` packages existing compiled assets. Do not distribute output from the personal `scripts/release/build_exe.ps1` workflow without checking its copied `.env`. See [SECURITY.md](../SECURITY.md).

## Troubleshooting

- Missing window: compile with `build:app` and verify `node_modules/.bin/electron.cmd` exists.
- Missing state updates: verify Aiden is running on port 5000 and the `/api/v1/ws` connection succeeds.
- Type/build failures: use the documented Node baseline and reproduce dependencies with `npm ci`.
- The transparent window may not have standard controls; stop Aiden through its tray/stop workflow.

The overlay uses React 19, TypeScript, Framer Motion, Electron, and Vite. It is separate from the React 18 dashboard.


### Live voice captions
PC microphone capture now feeds a bounded, display-only Vosk worker from the same cleaned PCM frames used by Whisper. No second microphone stream is opened. Whisper remains authoritative for commands; interim captions may change. If the local Vosk model is missing, final recognition still works.

Browser voice mode forwards Web Speech interim captions to the desktop overlay. Dictation in text mode remains silent and does not open the overlay.

Edge TTS supplies word boundaries with its audio. Boundaries are cached by audio hash and the current word follows pygame's playback position on PC or the browser Audio.currentTime on the device. Browser playback IDs reject stale events and permit autoplay retries. Long captions advance to keep the spoken word visible. Google/offline audio keeps full captions when no word boundaries are available; no fabricated timing is used. Restart Aiden and its overlay after rebuilding; reload dashboard tabs.
