const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  getAppPath: () => ipcRenderer.invoke('get-app-path'),
  platform: process.platform
});
