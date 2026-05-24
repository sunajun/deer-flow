/// <reference types="vite/client" />

interface DeerFlowAPI {
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

declare global {
  interface Window {
    deerflow: DeerFlowAPI;
  }
}

export {};
