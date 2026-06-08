const { app, BrowserWindow, Menu, Tray, ipcMain } = require('electron');
const { spawn, execSync } = require('child_process');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'OverscrollHistoryNavigation');
app.commandLine.appendSwitch('disable-http-cache');

let mainWindow;
let trayWindow = null;
let djangoProcess;
let tray = null;
let forceQuit = false;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        title: 'AURORA',
        frame: false,
        backgroundColor: '#000000',
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
        },
        icon: path.join(__dirname, 'music/static/music/images/favicon.png'),
    });

    Menu.setApplicationMenu(null);

    try {
        execSync('for /f "tokens=5" %a in (\'netstat -aon ^| findstr :8000 ^| findstr LISTENING\') do taskkill /F /PID %a', { stdio: 'ignore' });
    } catch (e) {
        // No existing process on port 8000.
    }

    djangoProcess = spawn('python', ['manage.py', 'runserver', '--noreload'], {
        cwd: __dirname,
        shell: true,
        stdio: 'inherit',
        env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });

    const iconPath = path.join(__dirname, 'music/static/music/images/favicon.png');
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
            preload: path.join(__dirname, 'preload.js'),
        },
    });
    trayWindow.loadFile(path.join(__dirname, 'tray_menu.html'));

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
            mainWindow.loadURL(`http://127.0.0.1:8000/?t=${Date.now()}`).catch(() => {
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
        spawn('taskkill', ['/pid', djangoProcess.pid, '/f', '/t']);
    }
});
