import { app, BrowserWindow, screen } from 'electron';
import path from 'path';

process.env.DIST = path.join(__dirname, '../dist');
process.env.VITE_PUBLIC = app.isPackaged ? process.env.DIST : path.join(process.env.DIST, '../public');

let win: BrowserWindow | null;
// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL'];

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
        x: xPosition, // center horizontally, clamped to screen bounds
        y: 0, // top
        title: 'Aiden Overlay',
        icon: path.join(process.env.VITE_PUBLIC as string, 'icon.ico'),
        transparent: true,
        frame: false,
        alwaysOnTop: true,
        skipTaskbar: false, // Show in task manager with proper name
        resizable: false,
        hasShadow: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
        },
    });

    // Test active push message to Renderer-process.
    win.setIgnoreMouseEvents(true, { forward: true });
    win.webContents.on('did-finish-load', () => {
        win?.webContents.send('main-process-message', (new Date).toLocaleString());
    });

    if (VITE_DEV_SERVER_URL) {
        win.loadURL(VITE_DEV_SERVER_URL);
    } else {
        // win.loadFile('dist/index.html')
        win.loadFile(path.join(process.env.DIST as string, 'index.html'));
    }
}

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

app.whenReady().then(createWindow);
