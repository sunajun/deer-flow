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
  vmStart(config?: any): Promise<boolean>;
  vmStop(): Promise<boolean>;
  vmExecute(command: string, timeout?: number): Promise<any>;
  vmPause(): Promise<boolean>;
  vmResume(): Promise<boolean>;
  vmSaveSnapshot(name: string): Promise<boolean>;
  vmRestoreSnapshot(name: string): Promise<boolean>;
  vmListSnapshots(): Promise<any[]>;
  vmDeleteSnapshot(name: string): Promise<boolean>;
  vmDefaultConfig(): Promise<any>;
  onVMState(callback: (state: string) => void): void;
  onVMSupport(callback: (support: any) => void): void;
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

  vmStart: (config?: any) => ipcRenderer.invoke("vm-start", config),
  vmStop: () => ipcRenderer.invoke("vm-stop"),
  vmExecute: (command: string, timeout?: number) => ipcRenderer.invoke("vm-execute", command, timeout),
  vmPause: () => ipcRenderer.invoke("vm-pause"),
  vmResume: () => ipcRenderer.invoke("vm-resume"),
  vmSaveSnapshot: (name: string) => ipcRenderer.invoke("vm-save-snapshot", name),
  vmRestoreSnapshot: (name: string) => ipcRenderer.invoke("vm-restore-snapshot", name),
  vmListSnapshots: () => ipcRenderer.invoke("vm-list-snapshots"),
  vmDeleteSnapshot: (name: string) => ipcRenderer.invoke("vm-delete-snapshot", name),
  vmDefaultConfig: () => ipcRenderer.invoke("vm-default-config"),

  onVMState: (callback: (state: string) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, state: string) => callback(state);
    ipcRenderer.on("vm-state", listener);
    return () => ipcRenderer.removeListener("vm-state", listener);
  },

  onVMSupport: (callback: (support: any) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, support: any) => callback(support);
    ipcRenderer.on("vm-support", listener);
    return () => ipcRenderer.removeListener("vm-support", listener);
  },
});
