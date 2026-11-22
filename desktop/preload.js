const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("riotDesktop", {
  isDesktop: true,
  platform: process.platform,
  pickFolder: (defaultPath) => ipcRenderer.invoke("riot:pick-folder", defaultPath || ""),
  switchTab: (tab) => ipcRenderer.send("riot:switch-tab", tab),
  windowAction: (action) => ipcRenderer.send("riot:window-action", action),
  getStatus: () => ipcRenderer.invoke("riot:get-status"),
  updateBackend: () => ipcRenderer.invoke("riot:update-backend"),
  restartBackend: () => ipcRenderer.invoke("riot:restart-backend"),
  openExternal: (url) => ipcRenderer.send("riot:open-external", url),
  onStatus: (cb) => {
    if (typeof cb !== "function") return () => {};
    const handler = (_ev, payload) => cb(payload);
    ipcRenderer.on("riot:status", handler);
    return () => ipcRenderer.removeListener("riot:status", handler);
  },
});
