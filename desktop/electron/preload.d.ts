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
  installUpdate(): void;
}

declare global {
  interface Window {
    deerflow: DeerFlowAPI;
  }
}
