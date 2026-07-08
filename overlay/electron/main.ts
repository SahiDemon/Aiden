import { app, BrowserWindow, ipcMain, screen } from 'electron';
import { spawn, type ChildProcess } from 'child_process';
import path from 'path';
import os from 'os';

process.env.DIST = path.join(__dirname, '../dist');
process.env.VITE_PUBLIC = app.isPackaged ? process.env.DIST : path.join(process.env.DIST, '../public');

let win: BrowserWindow | null;
let backendProcess: ChildProcess | null = null;
// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL'];

const DEBUG_FLAGS = new Set(['--debug', '-debug']);
const isDebugMode = process.argv.some((arg) => DEBUG_FLAGS.has(arg));

const userDataDir = path.join(os.homedir(), 'AppData', 'Local', 'Aiden');
app.setPath('userData', userDataDir);
app.setPath('sessionData', path.join(userDataDir, 'Session'));
app.commandLine.appendSwitch('disk-cache-dir', path.join(userDataDir, 'Cache'));
app.commandLine.appendSwitch('media-cache-dir', path.join(userDataDir, 'Cache', 'Media'));

function resolveBackendExecutable(): { exePath: string; exeArgs: string[]; cwd: string } | null {
    if (!app.isPackaged) {
        return null;
    }

    const backendRoot = path.join(process.resourcesPath, 'backend', 'Aiden');
    return {
        exePath: path.join(backendRoot, 'Aiden.exe'),
        exeArgs: isDebugMode ? ['--debug'] : [],
        cwd: backendRoot,
    };
}

function startBackend() {
    const backend = resolveBackendExecutable();
    if (!backend) {
        return;
    }

    if (backendProcess && !backendProcess.killed) {
        return;
    }

    const env: NodeJS.ProcessEnv = {
        ...process.env,
        AIDEN_EMBEDDED_OVERLAY: '1',
    };

    if (isDebugMode) {
        env.APP_DEBUG = 'true';
    }

    backendProcess = spawn(backend.exePath, backend.exeArgs, {
        cwd: backend.cwd,
        env,
        stdio: isDebugMode ? 'inherit' : 'ignore',
        windowsHide: !isDebugMode,
    });

    backendProcess.on('exit', () => {
        backendProcess = null;
    });
}

function keepOverlayOnTop() {
    if (!win || win.isDestroyed()) {
        return;
    }

    win.setAlwaysOnTop(true, 'screen-saver', 1);
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    win.showInactive();
    win.moveTop();
}

function hideOverlay() {
    if (!win || win.isDestroyed()) {
        return;
    }

    // Do not call win.hide() to prevent dropping the Chromium GPU context.
    // The React app handles the opacity and animations, so it will be visually hidden.
    // Ensure mouse events pass through the invisible window.
    win.setIgnoreMouseEvents(true, { forward: true });
}

function createWindow() {
    const { width: screenWidth } = screen.getPrimaryDisplay().workAreaSize;
    const maxNotchWidth = 1920;
    const notchHeight = 200;
    
    // Ensure window width never exceeds screen width
    const windowWidth = Math.min(maxNotchWidth, screenWidth);
    // Center horizontally, but clamp to 0 to prevent negative x-position
    const xPosition = Math.max(0, (screenWidth - windowWidth) / 2);

    win = new BrowserWindow({
        width: windowWidth,
        height: notchHeight,
        x: xPosition, 
        y: 0, 
        title: 'Aiden Overlay',
        icon: path.join(process.env.VITE_PUBLIC as string, 'icon.ico'),
        transparent: true,
        frame: false,
        show: false,
        alwaysOnTop: true,
        skipTaskbar: true, 
        resizable: false,
        hasShadow: false,
        focusable: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
    });

    // Test active push message to Renderer-process.
    win.setIgnoreMouseEvents(true, { forward: true });
    win.on('blur', keepOverlayOnTop);
    win.webContents.on('did-finish-load', () => {
        win?.webContents.send('main-process-message', (new Date).toLocaleString());
    });

    if (isDebugMode) {
        win.webContents.openDevTools({ mode: 'detach' });
    }

    if (VITE_DEV_SERVER_URL) {
        win.loadURL(VITE_DEV_SERVER_URL);
    } else {
        // win.loadFile('dist/index.html')
        win.loadFile(path.join(process.env.DIST as string, 'index.html'));
    }
}

ipcMain.on('overlay:raise', keepOverlayOnTop);
ipcMain.on('overlay:hide', hideOverlay);

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
        win = null;
    }
});

app.on('activate', () => {
    // On OS X it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

app.whenReady().then(() => {
    startBackend();
    createWindow();
});

app.on('before-quit', () => {
    if (backendProcess && !backendProcess.killed) {
        backendProcess.kill();
    }
});
