import { contextBridge, ipcRenderer } from "electron";

export interface DeerFlowAPI {
  getPlatform(): Promise<string>;
  getAppVersion(): Promise<string>;
  onBackendStatus(callback: (status: string) => void): () => void;
  onBackendPort(callback: (port: number) => void): () => void;
  restartBackend(): Promise<void>;
  detectSandbox(): Promise<{ type: string; available: boolean }>;
  selectDirectory(): Promise<string | null>;
  openInExplorer(path: string): void;
  onDeepLink(callback: (url: string) => void): () => void;
  onUpdateAvailable(callback: (info: any) => void): () => void;
  onUpdateDownloaded(callback: () => void): () => void;
  onUpdateError(callback: (error: any) => void): () => void;
  onUpdateDownloadProgress(callback: (progress: any) => void): () => void;
  installUpdate(): void;
  checkForUpdates(): Promise<void>;
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
  onVMState(callback: (state: string) => void): () => void;
  onVMSupport(callback: (support: any) => void): () => void;
  wsl2Detect(): Promise<any>;
  wsl2Install(): Promise<any>;
  wsl2WizardDetect(): Promise<any>;
  wsl2WizardResume(): Promise<any>;
  wsl2WorkspaceSetup(mode: string): Promise<any>;
  wsl2WorkspaceVerify(): Promise<any>;
  wsl2DistroUpdate(imagePath: string): Promise<any>;
  wsl2DistroVersion(): Promise<any>;
  wsl2DistroHealth(): Promise<any>;
  onWSL2Support(callback: (support: any) => void): () => void;
  onWSL2InstallProgress(callback: (progress: any) => void): () => void;
  onWSL2WizardStatus(callback: (status: any) => void): () => void;
  onWSL2Error(callback: (error: any) => void): () => void;
  onConsoleLog(callback: (entries: any[]) => void): () => void;
  setConsoleOpen(open: boolean): void;
  getRecentLogs(count?: number): Promise<any[]>;
  clearLogs(): Promise<boolean>;
  exportLogs(): Promise<string | null>;
  openSettings(): void;
  getSettings(): Promise<any>;
  saveSettings(settings: any): Promise<boolean>;
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

  onUpdateError: (callback: (error: any) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, error: any) => callback(error);
    ipcRenderer.on("update-error", listener);
    return () => ipcRenderer.removeListener("update-error", listener);
  },

  onUpdateDownloadProgress: (callback: (progress: any) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, progress: any) => callback(progress);
    ipcRenderer.on("update-download-progress", listener);
    return () => ipcRenderer.removeListener("update-download-progress", listener);
  },

  installUpdate: () => ipcRenderer.send("install-update"),
  checkForUpdates: () => ipcRenderer.invoke("check-for-updates"),

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

  wsl2Detect: () => ipcRenderer.invoke("wsl2-detect"),
  wsl2Install: () => ipcRenderer.invoke("wsl2-install"),
  wsl2WizardDetect: () => ipcRenderer.invoke("wsl2-wizard-detect"),
  wsl2WizardResume: () => ipcRenderer.invoke("wsl2-wizard-resume"),
  wsl2WorkspaceSetup: (mode: string) => ipcRenderer.invoke("wsl2-workspace-setup", mode),
  wsl2WorkspaceVerify: () => ipcRenderer.invoke("wsl2-workspace-verify"),
  wsl2DistroUpdate: (imagePath: string) => ipcRenderer.invoke("wsl2-distro-update", imagePath),
  wsl2DistroVersion: () => ipcRenderer.invoke("wsl2-distro-version"),
  wsl2DistroHealth: () => ipcRenderer.invoke("wsl2-distro-health"),

  onWSL2Support: (callback: (support: any) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, support: any) => callback(support);
    ipcRenderer.on("wsl2-support", listener);
    return () => ipcRenderer.removeListener("wsl2-support", listener);
  },

  onWSL2InstallProgress: (callback: (progress: any) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, progress: any) => callback(progress);
    ipcRenderer.on("wsl2-install-progress", listener);
    return () => ipcRenderer.removeListener("wsl2-install-progress", listener);
  },

  onWSL2WizardStatus: (callback: (status: any) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, status: any) => callback(status);
    ipcRenderer.on("wsl2-wizard-status", listener);
    return () => ipcRenderer.removeListener("wsl2-wizard-status", listener);
  },

  onWSL2Error: (callback: (error: any) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, error: any) => callback(error);
    ipcRenderer.on("wsl2-error", listener);
    return () => ipcRenderer.removeListener("wsl2-error", listener);
  },

  onConsoleLog: (callback: (entries: any[]) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, entries: any[]) => callback(entries);
    ipcRenderer.on("console:log", listener);
    return () => ipcRenderer.removeListener("console:log", listener);
  },

  setConsoleOpen: (open: boolean) => ipcRenderer.send("console:set-open", open),
  getRecentLogs: (count?: number) => ipcRenderer.invoke("console:get-recent-logs", count),
  clearLogs: () => ipcRenderer.invoke("console:clear-logs"),
  exportLogs: () => ipcRenderer.invoke("console:export-logs"),

  openSettings: () => ipcRenderer.send("open-settings"),
  getSettings: () => ipcRenderer.invoke("get-settings"),
  saveSettings: (settings: any) => ipcRenderer.invoke("save-settings", settings),
});
