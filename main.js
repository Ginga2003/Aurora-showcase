const { app, BrowserWindow, Menu, Tray, ipcMain, dialog } = require('electron');
const { spawn, spawnSync, execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'OverscrollHistoryNavigation');
app.commandLine.appendSwitch('disable-http-cache');

let mainWindow;
let trayWindow = null;
let djangoProcess;
let tray = null;
let forceQuit = false;
let appRoot = __dirname;
let runtimeDir = __dirname;
let runtimeEnv = process.env;
let pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
let djangoLogPath = null;

const SERVER_HOST = '127.0.0.1';
const SERVER_PORT = '8000';
const SERVER_URL = `http://${SERVER_HOST}:${SERVER_PORT}`;
const PLACEHOLDER_MEDIA = [
    'avatars/default.jpeg',
    'covers/default_cover.jpg',
    'playlists/default_playlist.png',
    'playlists/Favourite.png',
];

function ensureDirectory(targetPath) {
    fs.mkdirSync(targetPath, { recursive: true });
}

function appendStartupLog(message) {
    if (!djangoLogPath) return;
    const line = `[${new Date().toISOString()}] ${message}\n`;
    fs.appendFileSync(djangoLogPath, line, 'utf8');
}

function getPythonExecutable() {
    if (app.isPackaged) {
        const bundledPython = path.join(process.resourcesPath, 'python', process.platform === 'win32' ? 'python.exe' : 'python');
        if (fs.existsSync(bundledPython)) {
            return bundledPython;
        }
    }
    return process.platform === 'win32' ? 'python' : 'python3';
}

function copyPlaceholderMedia() {
    const sourceMediaRoot = path.join(appRoot, 'media');
    const targetMediaRoot = path.join(runtimeDir, 'media');

    for (const relativePath of PLACEHOLDER_MEDIA) {
        const sourcePath = path.join(sourceMediaRoot, relativePath);
        const targetPath = path.join(targetMediaRoot, relativePath);
        ensureDirectory(path.dirname(targetPath));
        if (fs.existsSync(sourcePath) && !fs.existsSync(targetPath)) {
            fs.copyFileSync(sourcePath, targetPath);
        }
    }

    for (const folder of ['avatars', 'covers', 'lyrics', 'playlists', 'songs']) {
        ensureDirectory(path.join(targetMediaRoot, folder));
    }
}

function runManageCommand(args, label) {
    appendStartupLog(`Running manage.py ${args.join(' ')}`);
    const result = spawnSync(pythonExecutable, ['manage.py', ...args], {
        cwd: appRoot,
        env: runtimeEnv,
        encoding: 'utf8',
        shell: false,
        windowsHide: true,
    });

    if (result.stdout) appendStartupLog(result.stdout.trimEnd());
    if (result.stderr) appendStartupLog(result.stderr.trimEnd());

    if (result.error) {
        throw new Error(`${label} failed: ${result.error.message}`);
    }
    if (result.status !== 0) {
        throw new Error(`${label} failed with exit code ${result.status}. See ${djangoLogPath} for details.`);
    }
}

function prepareDjangoRuntime() {
    appRoot = app.getAppPath();
    runtimeDir = app.isPackaged ? app.getPath('userData') : appRoot;
    ensureDirectory(runtimeDir);
    djangoLogPath = path.join(runtimeDir, 'aurora-django.log');
    pythonExecutable = getPythonExecutable();
    runtimeEnv = {
        ...process.env,
        AURORA_APP_DATA_DIR: runtimeDir,
        DJANGO_ALLOWED_HOSTS: `${SERVER_HOST},localhost`,
        DJANGO_DEBUG: '1',
        DJANGO_SECRET_KEY: process.env.DJANGO_SECRET_KEY || 'django-insecure-showcase-local-desktop-only',
        PYTHONUNBUFFERED: '1',
    };

    copyPlaceholderMedia();

    const databasePath = path.join(runtimeDir, 'db.sqlite3');
    const seedMarkerPath = path.join(runtimeDir, '.showcase_seeded');

    runManageCommand(['migrate', '--noinput'], 'Database migration');

    if (app.isPackaged && !fs.existsSync(seedMarkerPath)) {
        runManageCommand(['seed_showcase', '--with-admin'], 'Showcase seed');
        fs.writeFileSync(seedMarkerPath, new Date().toISOString(), 'utf8');
    }
}

function stopExistingServer() {
    if (process.platform !== 'win32') return;
    try {
        execSync(`for /f "tokens=5" %a in ('netstat -aon ^| findstr :${SERVER_PORT} ^| findstr LISTENING') do taskkill /F /PID %a`, { stdio: 'ignore' });
    } catch (e) {
        // No existing process on the Aurora port.
    }
}

function startDjangoServer() {
    const logFd = app.isPackaged ? fs.openSync(djangoLogPath, 'a') : null;
    const stdio = app.isPackaged ? ['ignore', logFd, logFd] : 'inherit';

    djangoProcess = spawn(pythonExecutable, ['manage.py', 'runserver', `${SERVER_HOST}:${SERVER_PORT}`, '--noreload'], {
        cwd: appRoot,
        shell: false,
        stdio,
        env: runtimeEnv,
        windowsHide: true,
    });

    djangoProcess.on('error', (error) => {
        appendStartupLog(`Django process error: ${error.message}`);
    });
}

function showStartupError(error) {
    const logHint = djangoLogPath ? `\n\nLog file: ${djangoLogPath}` : '';
    dialog.showErrorBox('Aurora Showcase failed to start', `${error.message}${logHint}`);
    app.quit();
}

function appPath(relativePath) {
    return path.join(appRoot, relativePath);
}

function createWindow() {
    try {
        stopExistingServer();
        prepareDjangoRuntime();
        startDjangoServer();
    } catch (error) {
        showStartupError(error);
        return;
    }

    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        title: 'AURORA',
        frame: false,
        backgroundColor: '#000000',
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: appPath('preload.js'),
        },
        icon: appPath('music/static/music/images/favicon.png'),
    });

    Menu.setApplicationMenu(null);

    const iconPath = appPath('music/static/music/images/favicon.png');
    tray = new Tray(iconPath);
    tray.setToolTip('AURORA');

    trayWindow = new BrowserWindow({
        width: 200,
        height: 104,
        show: false,
        frame: false,
        fullscreenable: false,
        resizable: false,
        transparent: true,
        skipTaskbar: true,
        alwaysOnTop: true,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: appPath('preload.js'),
        },
    });
    trayWindow.loadFile(appPath('tray_menu.html'));

    let lastBlurTime = 0;
    let isTrayMenuVisible = false;

    const hideTray = () => {
        isTrayMenuVisible = false;
        if (!trayWindow) return;
        trayWindow.setOpacity(0);
        setTimeout(() => {
            if (!isTrayMenuVisible && trayWindow) {
                trayWindow.setPosition(-10000, -10000);
            }
        }, 50);
    };

    trayWindow.on('blur', () => {
        lastBlurTime = Date.now();
        hideTray();
    });

    tray.on('click', () => {
        if (mainWindow) mainWindow.show();
    });

    tray.on('right-click', () => {
        if (isTrayMenuVisible) {
            hideTray();
            return;
        }
        if (Date.now() - lastBlurTime < 200) return;

        const { screen } = require('electron');
        const cursorPoint = screen.getCursorScreenPoint();
        const display = screen.getDisplayNearestPoint(cursorPoint);
        const bounds = trayWindow.getBounds();
        let x = cursorPoint.x - bounds.width / 2;
        let y = cursorPoint.y - bounds.height - 25;

        if (x + bounds.width > display.workArea.x + display.workArea.width) {
            x = display.workArea.x + display.workArea.width - bounds.width - 5;
        }
        if (y < display.workArea.y) {
            y = cursorPoint.y + 10;
        }

        trayWindow.setPosition(Math.round(x), Math.round(y), false);
        trayWindow.setOpacity(1);
        if (!trayWindow.isVisible()) {
            trayWindow.show();
        }
        trayWindow.focus();
        isTrayMenuVisible = true;
    });

    ipcMain.on('show-main', () => {
        if (mainWindow) mainWindow.show();
        if (trayWindow) hideTray();
    });

    ipcMain.on('quit-app', () => {
        forceQuit = true;
        app.quit();
    });

    ipcMain.on('window-minimize', () => {
        if (mainWindow) mainWindow.minimize();
    });

    ipcMain.on('window-maximize', () => {
        if (!mainWindow) return;
        if (mainWindow.isMaximized()) {
            mainWindow.unmaximize();
        } else {
            mainWindow.maximize();
        }
    });

    ipcMain.on('window-close', () => {
        if (!mainWindow) return;
        if (!forceQuit) {
            mainWindow.hide();
        } else {
            mainWindow.close();
        }
    });

    mainWindow.on('close', (event) => {
        if (!forceQuit) {
            event.preventDefault();
            mainWindow.hide();
        }
    });

    mainWindow.on('maximize', () => {
        mainWindow.webContents.send('window-maximized');
    });

    mainWindow.on('unmaximize', () => {
        mainWindow.webContents.send('window-unmaximized');
    });

    mainWindow.once('ready-to-show', () => {
        if (mainWindow.isMaximized()) {
            mainWindow.webContents.send('window-maximized');
        }
    });

    let initialLoadComplete = false;

    const tryLoad = () => {
        if (!mainWindow) return;
        mainWindow.webContents.session.clearCache().then(() => {
            mainWindow.loadURL(`${SERVER_URL}/?t=${Date.now()}`).catch(() => {
                setTimeout(tryLoad, 1000);
            });
        });
    };

    mainWindow.webContents.on('did-finish-load', () => {
        initialLoadComplete = true;
    });

    tryLoad();

    mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL, isMainFrame) => {
        if (isMainFrame === false || errorCode === -3 || initialLoadComplete) return;
        setTimeout(tryLoad, 1000);
    });
}

app.on('ready', createWindow);

app.on('will-quit', () => {
    if (djangoProcess) {
        if (process.platform === 'win32') {
            spawn('taskkill', ['/pid', djangoProcess.pid, '/f', '/t'], { windowsHide: true });
        } else {
            djangoProcess.kill();
        }
    }
});
