import { autoUpdater, UpdateInfo } from "electron-updater";
import { app, BrowserWindow, dialog } from "electron";
import { Logger } from "./logger";

export interface UpdaterEvents {
  onUpdateAvailable(info: UpdateInfo): void;
  onUpdateDownloaded(): void;
  onUpdateError(error: Error): void;
  onDownloadProgress(progress: { percent: number; transferred: number; total: number }): void;
}

const INITIAL_CHECK_DELAY = 30_000;
const CHECK_INTERVAL = 4 * 60 * 60 * 1000;

export class DeerFlowUpdater {
  private logger: Logger;
  private checkTimer: NodeJS.Timeout | null = null;
  private listeners: Partial<UpdaterEvents> = {};
  private downloadedInfo: UpdateInfo | null = null;
  private isChecking = false;

  constructor(logger: Logger) {
    this.logger = logger;
    this.configure();
    this.setupEvents();
  }

  private configure(): void {
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.allowPrerelease = false;

    if (process.platform === "linux") {
      autoUpdater.autoInstallOnAppQuit = false;
    }
  }

  private setupEvents(): void {
    autoUpdater.on("update-available", (info) => {
      this.logger.info("electron", `Update available: v${info.version}`);
      this.downloadedInfo = info;
      this.listeners.onUpdateAvailable?.(info);

      const windows = BrowserWindow.getAllWindows();
      for (const win of windows) {
        if (!win.isDestroyed()) {
          win.webContents.send("update-available", info);
        }
      }

      if (process.platform !== "linux") {
        this.downloadUpdate();
      }
    });

    autoUpdater.on("update-not-available", () => {
      this.logger.info("electron", "No update available");
      this.isChecking = false;
    });

    autoUpdater.on("download-progress", (progress) => {
      this.logger.debug("electron", `Download progress: ${progress.percent.toFixed(1)}%`);
      this.listeners.onDownloadProgress?.({
        percent: progress.percent,
        transferred: progress.transferred,
        total: progress.total,
      });

      const windows = BrowserWindow.getAllWindows();
      for (const win of windows) {
        if (!win.isDestroyed()) {
          win.webContents.send("update-download-progress", {
            percent: progress.percent,
            transferred: progress.transferred,
            total: progress.total,
          });
        }
      }
    });

    autoUpdater.on("update-downloaded", () => {
      this.logger.info("electron", "Update downloaded");
      this.listeners.onUpdateDownloaded?.();

      const windows = BrowserWindow.getAllWindows();
      for (const win of windows) {
        if (!win.isDestroyed()) {
          win.webContents.send("update-downloaded");
        }
      }
    });

    autoUpdater.on("error", (error) => {
      this.logger.error("electron", "Update error", error.message);
      this.isChecking = false;
      this.listeners.onUpdateError?.(error);

      const windows = BrowserWindow.getAllWindows();
      for (const win of windows) {
        if (!win.isDestroyed()) {
          win.webContents.send("update-error", { message: error.message });
        }
      }
    });
  }

  on<K extends keyof UpdaterEvents>(event: K, listener: UpdaterEvents[K]): void {
    this.listeners[event] = listener;
  }

  startPeriodicCheck(): void {
    setTimeout(() => {
      this.checkForUpdates();
    }, INITIAL_CHECK_DELAY);

    this.checkTimer = setInterval(() => {
      this.checkForUpdates();
    }, CHECK_INTERVAL);
  }

  async checkForUpdates(): Promise<void> {
    if (this.isChecking) return;
    if (process.platform === "linux") {
      this.logger.info("electron", "Linux does not support auto-update, please download manually");
      return;
    }

    this.isChecking = true;
    try {
      await autoUpdater.checkForUpdates();
    } catch (err) {
      this.logger.error("electron", "Check for updates failed", err);
    } finally {
      this.isChecking = false;
    }
  }

  async downloadUpdate(): Promise<void> {
    try {
      this.logger.info("electron", "Starting update download...");
      await autoUpdater.downloadUpdate();
    } catch (err) {
      this.logger.error("electron", "Download update failed", err);
    }
  }

  async installUpdate(): Promise<void> {
    if (process.platform === "linux") {
      this.logger.info("electron", "Linux: please download the new version manually");
      return;
    }

    const windows = BrowserWindow.getAllWindows();
    const mainWindow = windows[0];

    if (mainWindow && !mainWindow.isDestroyed()) {
      const result = await dialog.showMessageBox(mainWindow, {
        type: "info",
        title: "Install Update",
        message: "Update downloaded. Restart DeerFlow to install the update?",
        buttons: ["Restart Now", "Later"],
        defaultId: 0,
      });

      if (result.response === 0) {
        this.logger.info("electron", "Installing update and restarting...");
        setImmediate(() => autoUpdater.quitAndInstall());
      }
    } else {
      setImmediate(() => autoUpdater.quitAndInstall());
    }
  }

  getDownloadedInfo(): UpdateInfo | null {
    return this.downloadedInfo;
  }

  stopPeriodicCheck(): void {
    if (this.checkTimer) {
      clearInterval(this.checkTimer);
      this.checkTimer = null;
    }
  }

  destroy(): void {
    this.stopPeriodicCheck();
    this.listeners = {};
  }
}
