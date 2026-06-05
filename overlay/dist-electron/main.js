"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const os_1 = __importDefault(require("os"));
process.env.DIST = path_1.default.join(__dirname, '../dist');
process.env.VITE_PUBLIC = electron_1.app.isPackaged ? process.env.DIST : path_1.default.join(process.env.DIST, '../public');
let win;
let backendProcess = null;
// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL'];
const DEBUG_FLAGS = new Set(['--debug', '-debug']);
const isDebugMode = process.argv.some((arg) => DEBUG_FLAGS.has(arg));
const userDataDir = path_1.default.join(os_1.default.homedir(), 'AppData', 'Local', 'Aiden');
electron_1.app.setPath('userData', userDataDir);
electron_1.app.setPath('sessionData', path_1.default.join(userDataDir, 'Session'));
electron_1.app.commandLine.appendSwitch('disk-cache-dir', path_1.default.join(userDataDir, 'Cache'));
electron_1.app.commandLine.appendSwitch('media-cache-dir', path_1.default.join(userDataDir, 'Cache', 'Media'));
function resolveBackendExecutable() {
    if (!electron_1.app.isPackaged) {
        return null;
    }
    const backendRoot = path_1.default.join(process.resourcesPath, 'backend', isDebugMode ? 'AidenConsole' : 'Aiden');
    const exeName = isDebugMode ? 'AidenConsole.exe' : 'Aiden.exe';
    return {
        exePath: path_1.default.join(backendRoot, exeName),
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
    const env = {
        ...process.env,
        AIDEN_EMBEDDED_OVERLAY: '1',
    };
    if (isDebugMode) {
        env.APP_DEBUG = 'true';
    }
    backendProcess = (0, child_process_1.spawn)(backend.exePath, [], {
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
    win.hide();
}
function createWindow() {
    const { width: screenWidth } = electron_1.screen.getPrimaryDisplay().workAreaSize;
    const maxNotchWidth = 1920;
    const notchHeight = 200;
    // Ensure window width never exceeds screen width
    const windowWidth = Math.min(maxNotchWidth, screenWidth);
    // Center horizontally, but clamp to 0 to prevent negative x-position
    const xPosition = Math.max(0, (screenWidth - windowWidth) / 2);
    win = new electron_1.BrowserWindow({
        width: windowWidth,
        height: notchHeight,
        x: xPosition,
        y: 0,
        title: 'Aiden Overlay',
        icon: path_1.default.join(process.env.VITE_PUBLIC, 'icon.ico'),
        transparent: true,
        frame: false,
        show: false,
        alwaysOnTop: true,
        skipTaskbar: true,
        resizable: false,
        hasShadow: false,
        focusable: false,
        webPreferences: {
            preload: path_1.default.join(__dirname, 'preload.js'),
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
    if (VITE_DEV_SERVER_URL) {
        win.loadURL(VITE_DEV_SERVER_URL);
    }
    else {
        // win.loadFile('dist/index.html')
        win.loadFile(path_1.default.join(process.env.DIST, 'index.html'));
    }
}
electron_1.ipcMain.on('overlay:raise', keepOverlayOnTop);
electron_1.ipcMain.on('overlay:hide', hideOverlay);
// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
electron_1.app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        electron_1.app.quit();
        win = null;
    }
});
electron_1.app.on('activate', () => {
    // On OS X it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (electron_1.BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});
electron_1.app.whenReady().then(() => {
    startBackend();
    createWindow();
});
electron_1.app.on('before-quit', () => {
    if (backendProcess && !backendProcess.killed) {
        backendProcess.kill();
    }
});
