# Aiden Overlay

A beautiful, transparent overlay window that displays Aiden's status at the top of your screen with animated liquid wave effects.

## Features

- 🌊 **Liquid Wave Animation** - Smooth, organic wave animations that respond to Aiden's state
- 🎨 **Dynamic States** - Visual feedback for listening, thinking, and replying states
- ✨ **Shimmer Text** - Elegant text animations with gradient effects
- 🪟 **Always On Top** - Transparent, frameless window that stays visible
- 🔌 **WebSocket Integration** - Real-time updates from Aiden backend
- 🎯 **Branded** - Shows as "Aiden Overlay" in task manager with custom icon

## Animation States

### Entry/Exit Animation
- **Entry**: Wave slides down from the top with fade-in effect
- **Exit**: Wave slides back up with fade-out (reverse of entry)

### State Animations
- **Listening**: Gentle, organic ripple effect
- **Thinking**: Smooth, deep breathing motion
- **Replying**: Natural, flowing wave pattern

## Setup

### Install Dependencies
```bash
npm install
```

### Development Mode
```bash
npm run dev
```

This runs both the Vite dev server and Electron in watch mode.

### Build for Production
```bash
npm run build
```

This compiles TypeScript, builds the Vite bundle, compiles Electron code, and packages the app.

## Auto-Launch with Aiden

The overlay **automatically launches** when you start Aiden! 

When you run `.\run_aiden.ps1`, the overlay will start automatically if it has been built. If the overlay isn't built, Aiden will skip it and show a warning in the logs.

To enable auto-launch:
1. Build the overlay: `npm run build` (in the overlay directory)
2. Start Aiden: `.\run_aiden.ps1`
3. The overlay will appear at the top of your screen

The overlay will automatically connect to Aiden's WebSocket server at `ws://localhost:5000/ws` and display real-time status updates.

## Configuration

The overlay connects to Aiden's API server on port 5000 by default. The WebSocket endpoint is configured in `src/hooks/useWebSocket.ts`.

### Window Settings
- **Width**: 1920px (centered horizontally)
- **Height**: 200px
- **Position**: Top center of screen
- **Transparency**: Enabled
- **Click-through**: Enabled (mouse events pass through)

## Tech Stack

- **React 19** - UI framework
- **TypeScript** - Type safety
- **Framer Motion** - Animation library
- **Electron** - Desktop app framework
- **Vite** - Build tool

## Project Structure

```
overlay/
├── src/
│   ├── components/
│   │   └── LiquidWave.tsx      # Main wave animation component
│   ├── hooks/
│   │   └── useWebSocket.ts     # WebSocket connection hook
│   ├── App.tsx                 # Main app component
│   └── main.tsx                # React entry point
├── electron/
│   ├── main.ts                 # Electron main process
│   └── preload.ts              # Electron preload script
└── dist-electron/              # Built Electron code (after build)
```

## Development Tips

- The overlay is frameless and transparent, so it won't have standard window controls
- Use the tray app or Ctrl+C in the terminal to stop Aiden (which will close the overlay)
- Hot reload works in development mode - changes to React components will update live
- Electron changes require a restart of the dev server

## Troubleshooting

### Overlay doesn't start automatically
- Make sure you've built the overlay: `npm run build`
- Check Aiden logs for overlay startup messages
- Verify `node_modules/.bin/electron.cmd` exists in the overlay directory

### Overlay doesn't show animations
- Check browser console for WebSocket connection errors
- Ensure Aiden's API server is running on port 5000
- Verify the WebSocket URL in `useWebSocket.ts` matches your API server

### Build errors
- Delete `node_modules` and run `npm install` again
- Make sure you have Node.js 18+ installed
- Check that all dependencies are compatible
