const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    minimize: () => ipcRenderer.send('window-minimize'),
    maximize: () => ipcRenderer.send('window-maximize'),
    close: () => ipcRenderer.send('window-close'),
    showMain: () => ipcRenderer.send('show-main'),
    quitApp: () => ipcRenderer.send('quit-app'),
    onMaximized: (callback) => ipcRenderer.on('window-maximized', callback),
    onUnmaximized: (callback) => ipcRenderer.on('window-unmaximized', callback)
});
