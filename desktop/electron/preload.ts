import { contextBridge, ipcRenderer } from "electron";

export interface DeerFlowAPI {
  getPlatform(): Promise<string>;
  getAppVersion(): Promise<string>;
  onBackendStatus(callback: (status: string) => void): void;
  onBackendPort(callback: (port: number) => void): void;
  restartBackend(): Promise<void>;
  detectSandbox(): Promise<{ type: string; available: boolean }>;
  selectDirectory(): Promise<string | null>;
  openInExplorer(path: string): void;
  onDeepLink(callback: (url: string) => void): void;
  onUpdateAvailable(callback: (info: any) => void): void;
  onUpdateDownloaded(callback: () => void): void;
  installUpdate(): void;
}

contextBridge.exposeInMainWorld("deerflow", {
  getPlatform: () => ipcRenderer.invoke("get-platform"),
  getAppVersion: () => ipcRenderer.invoke("get-app-version"),

  onBackendStatus: (callback: (status: string) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: string) => callback(status);
    ipcRenderer.on("backend-status", listener);
    return () => ipcRenderer.removeListener("backend-status", listener);
  },

  onBackendPort: (callback: (port: number) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, port: number) => callback(port);
    ipcRenderer.on("backend-port", listener);
    return () => ipcRenderer.removeListener("backend-port", listener);
  },

  restartBackend: () => ipcRenderer.invoke("restart-backend"),

  detectSandbox: () => ipcRenderer.invoke("detect-sandbox"),

  selectDirectory: () => ipcRenderer.invoke("select-directory"),

  openInExplorer: (path: string) => ipcRenderer.invoke("open-in-explorer", path),

  onDeepLink: (callback: (url: string) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, url: string) => callback(url);
    ipcRenderer.on("deep-link", listener);
    return () => ipcRenderer.removeListener("deep-link", listener);
  },

  onUpdateAvailable: (callback: (info: any) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, info: any) => callback(info);
    ipcRenderer.on("update-available", listener);
    return () => ipcRenderer.removeListener("update-available", listener);
  },

  onUpdateDownloaded: (callback: () => void) => {
    const listener = () => callback();
    ipcRenderer.on("update-downloaded", listener);
    return () => ipcRenderer.removeListener("update-downloaded", listener);
  },

  installUpdate: () => ipcRenderer.send("install-update"),
});
