import { app, BrowserWindow, ipcMain, shell, dialog } from "electron";
import path from "path";
import { PythonBackendManager } from "./python-backend";
import { VMSandboxManager, VirtualizationSupport, VMConfig } from "./vm-manager";
import { WSL2Sandbox, WSL2Error } from "../native/windows/wsl2-bridge";
import { WSL2Detector, WSL2Support } from "../native/windows/wsl2-detector";
import { WSL2SetupWizard, WizardStatus } from "../native/windows/wsl2-setup-wizard";
import { DistroManager } from "../native/windows/distro-manager";
import { WorkspaceMount, WorkspaceMode } from "../native/windows/workspace-mount";
import { DeerFlowTray, TrayStatus } from "./tray";
import { Logger } from "./logger";
import { DeerFlowUpdater } from "./updater";
import { IncrementalUpdater } from "./incremental-updater";

let mainWindow: BrowserWindow | null = null;
let tray: DeerFlowTray | null = null;
let backendManager: PythonBackendManager | null = null;
let vmManager: VMSandboxManager | null = null;
let vmSupport: VirtualizationSupport | null = null;
let wsl2Sandbox: WSL2Sandbox | null = null;
let wsl2Support: WSL2Support | null = null;
let wsl2Wizard: WSL2SetupWizard | null = null;
let distroManager: DistroManager | null = null;
let workspaceMount: WorkspaceMount | null = null;
let logger: Logger | null = null;
let updater: DeerFlowUpdater | null = null;
let incrementalUpdater: IncrementalUpdater | null = null;
let isQuitting = false;

const PROTOCOL = "deerflow";

const SETTINGS_FILE = "deerflow-settings.json";

function getSettingsPath(): string {
  return path.join(app.getPath("userData"), SETTINGS_FILE);
}

function loadSettings(): Record<string, unknown> {
  try {
    const fs = require("fs");
    const settingsPath = getSettingsPath();
    if (fs.existsSync(settingsPath)) {
      return JSON.parse(fs.readFileSync(settingsPath, "utf-8"));
    }
  } catch {
    // ignore
  }
  return {};
}

function saveSettingsToFile(settings: Record<string, unknown>): boolean {
  try {
    const fs = require("fs");
    const settingsPath = getSettingsPath();
    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2), "utf-8");
    return true;
  } catch {
    return false;
  }
}

function createMainWindow(): BrowserWindow {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "../dist-electron/preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
  });

  mainWindow.on("close", (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow?.hide();
    }
  });

  mainWindow.on("ready-to-show", () => {
    mainWindow?.show();
    mainWindow?.maximize();
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  return mainWindow;
}

function createTray(): void {
  tray = new DeerFlowTray({
    showMainWindow: () => {
      if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
      }
    },
    restartBackend: () => backendManager?.restart(),
    pauseSandbox: async () => vmManager?.pauseSandbox() ?? false,
    resumeSandbox: async () => vmManager?.resumeSandbox() ?? false,
    checkForUpdates: () => updater?.checkForUpdates(),
    openSettings: () => {
      if (mainWindow) {
        mainWindow.show();
        mainWindow.webContents.send("open-settings");
      }
    },
    quitApp: () => {
      isQuitting = true;
      app.quit();
    },
    getBackendStatus: () => backendManager?.status ?? "stopped",
    getSandboxType: () => {
      if (process.platform === "darwin" && vmSupport?.isSupported) return "virtualization-framework";
      if (process.platform === "win32" && wsl2Support?.wslInstalled) return "wsl2";
      return "local";
    },
    getSandboxState: () => {
      if (vmManager) return "running";
      if (wsl2Sandbox) return "running";
      return "stopped";
    },
    getAppVersion: () => app.getVersion(),
  });

  tray.create();
}

async function initVMSandbox(): Promise<void> {
  if (process.platform !== "darwin") return;

  vmManager = new VMSandboxManager();

  vmManager.on("state-change", (state: string) => {
    mainWindow?.webContents.send("vm-state", state);
    const trayStatus: TrayStatus = state === "running" ? "running" : state === "error" ? "error" : "stopped";
    tray?.setStatus(trayStatus);
  });

  try {
    vmSupport = await vmManager.detectSupport();
    mainWindow?.webContents.send("vm-support", vmSupport);

    if (!vmSupport.isSupported) {
      logger?.info("sandbox", "VM Sandbox not supported: " + vmSupport.reason);
      return;
    }

    logger?.info("sandbox", "Virtualization supported: " + vmSupport.chipArchitecture);
  } catch (err) {
    logger?.error("sandbox", "Detection failed", err);
  }
}

async function initWSL2Sandbox(): Promise<void> {
  if (process.platform !== "win32") return;

  wsl2Sandbox = new WSL2Sandbox();
  distroManager = new DistroManager(wsl2Sandbox);
  workspaceMount = new WorkspaceMount(wsl2Sandbox);

  wsl2Sandbox.on("state-change", (state: string) => {
    mainWindow?.webContents.send("vm-state", state);
    const trayStatus: TrayStatus = state === "running" ? "running" : state === "error" ? "error" : "stopped";
    tray?.setStatus(trayStatus);
  });

  try {
    const detector = new WSL2Detector();
    wsl2Support = await detector.detect();
    mainWindow?.webContents.send("wsl2-support", wsl2Support);

    if (wsl2Support.wslInstalled && wsl2Support.wsl2Default) {
      logger?.info("sandbox", "WSL2 is available");
    } else {
      logger?.info("sandbox", "WSL2 not available: " + wsl2Support.issues.join(", "));
    }
  } catch (err) {
    logger?.error("sandbox", "WSL2 Detection failed", err);
  }
}

async function startVMSandbox(config?: VMConfig): Promise<boolean> {
  if (!vmManager || !vmSupport?.isSupported) return false;

  try {
    if (!config) {
      const defaultConfig = await vmManager.getDefaultConfig();
      config = {
        imagePath: defaultConfig.imagePath || "",
        memoryMB: defaultConfig.memoryMB || 2048,
        cpuCount: defaultConfig.cpuCount || 2,
        workspacePath: defaultConfig.workspacePath || "",
        architecture: (defaultConfig.architecture as "apple_silicon" | "intel") || "apple_silicon",
      };
    }

    const id = await vmManager.createSandbox(config);
    const started = await vmManager.startSandbox(id);

    if (started) {
      logger?.info("sandbox", "VM Sandbox started, id: " + id);
      await vmManager.saveSnapshot("boot", id);
    }

    return started;
  } catch (err) {
    logger?.error("sandbox", "VM start failed", err);
    mainWindow?.webContents.send("vm-state", "error");
    return false;
  }
}

async function startWSL2Sandbox(imagePath?: string): Promise<boolean> {
  if (!wsl2Sandbox) return false;

  try {
    await wsl2Sandbox.init(imagePath);
    await wsl2Sandbox.start();
    logger?.info("sandbox", "WSL2 Sandbox started successfully");
    return true;
  } catch (err) {
    logger?.error("sandbox", "WSL2 start failed", err);
    if (err instanceof WSL2Error) {
      mainWindow?.webContents.send("wsl2-error", {
        code: err.code,
        message: err.message,
        suggestion: err.suggestion,
        recoverable: err.recoverable,
      });
    }
    return false;
  }
}

async function stopVMSandbox(): Promise<void> {
  if (!vmManager) return;
  try {
    await vmManager.stopSandbox();
    logger?.info("sandbox", "VM Sandbox stopped");
  } catch (err) {
    logger?.error("sandbox", "VM stop failed", err);
  }
}

async function stopWSL2Sandbox(): Promise<void> {
  if (!wsl2Sandbox) return;
  try {
    await wsl2Sandbox.stop();
    logger?.info("sandbox", "WSL2 Sandbox stopped");
  } catch (err) {
    logger?.error("sandbox", "WSL2 stop failed", err);
  }
}

async function restartVMSandbox(): Promise<void> {
  await stopVMSandbox();
  await startVMSandbox();
}

async function restartWSL2Sandbox(): Promise<void> {
  await stopWSL2Sandbox();
  await startWSL2Sandbox();
}

const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.on("ready", async () => {
    app.setAsDefaultProtocolClient(PROTOCOL);

    logger = new Logger();
    logger.info("electron", "DeerFlow starting...");

    incrementalUpdater = new IncrementalUpdater(logger);

    createMainWindow();

    if (process.platform === "darwin") {
      await initVMSandbox();
    } else if (process.platform === "win32") {
      await initWSL2Sandbox();
    }

    createTray();

    backendManager = new PythonBackendManager();

    backendManager.on("status", (status: string) => {
      mainWindow?.webContents.send("backend-status", status);
      const trayStatus: TrayStatus = status === "ready" ? "running" : status === "error" ? "error" : "stopped";
      tray?.setStatus(trayStatus);

      if (status === "ready") {
        tray?.notifyBackendReady();
      } else if (status === "error") {
        tray?.notifyBackendError();
      }
    });

    backendManager.on("port", (port: number) => {
      mainWindow?.webContents.send("backend-port", port);
      logger?.info("backend", "Backend listening on port " + port);
    });

    try {
      await backendManager.start();
    } catch (err) {
      logger?.error("backend", "Failed to start Python backend", err);
      mainWindow?.webContents.send("backend-status", "error");
    }

    if (app.isPackaged) {
      updater = new DeerFlowUpdater(logger);

      updater.on("onUpdateAvailable", (info) => {
        tray?.setUpdateAvailable(true);
        tray?.notifyUpdateAvailable(info.version);
      });

      updater.on("onUpdateDownloaded", () => {
        tray?.notifyUpdateDownloaded();
      });

      updater.startPeriodicCheck();
    }
  });

  app.on("before-quit", async () => {
    isQuitting = true;
    if (process.platform === "win32") {
      await stopWSL2Sandbox();
    } else {
      await stopVMSandbox();
    }
    if (backendManager) {
      await backendManager.stop();
    }
    logger?.info("electron", "DeerFlow shutting down");
    logger?.destroy();
    updater?.destroy();
    tray?.destroy();
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    } else {
      mainWindow?.show();
    }
  });

  app.on("open-url", (_event, url) => {
    mainWindow?.webContents.send("deep-link", url);
  });
}

ipcMain.handle("get-platform", () => process.platform);
ipcMain.handle("get-app-version", () => app.getVersion());

ipcMain.handle("restart-backend", async () => {
  await backendManager?.restart();
});

ipcMain.handle("detect-sandbox", async () => {
  if (process.platform === "darwin" && vmSupport) {
    return {
      type: "virtualization-framework",
      available: vmSupport.isSupported,
      chipArchitecture: vmSupport.chipArchitecture,
      supportedFeatures: vmSupport.supportedFeatures,
      reason: vmSupport.reason,
    };
  } else if (process.platform === "win32" && wsl2Support) {
    return {
      type: "wsl2",
      available: wsl2Support.wslInstalled && wsl2Support.wsl2Default,
      wslInstalled: wsl2Support.wslInstalled,
      wsl2Default: wsl2Support.wsl2Default,
      deerFlowDistroInstalled: wsl2Support.deerFlowDistroInstalled,
      canAutoInstall: wsl2Support.canAutoInstall,
      installMethod: wsl2Support.installMethod,
      issues: wsl2Support.issues,
      windowsVersion: wsl2Support.windowsVersion,
    };
  } else if (process.platform === "win32") {
    return { type: "wsl2", available: false };
  } else {
    return { type: "kvm", available: false };
  }
});

ipcMain.handle("vm-start", async (_event, config?: VMConfig) => {
  if (process.platform === "win32") {
    return await startWSL2Sandbox(config?.imagePath);
  }
  return await startVMSandbox(config);
});

ipcMain.handle("vm-stop", async () => {
  if (process.platform === "win32") {
    await stopWSL2Sandbox();
  } else {
    await stopVMSandbox();
  }
  return true;
});

ipcMain.handle("vm-execute", async (_event, command: string, timeout?: number) => {
  if (process.platform === "win32" && wsl2Sandbox) {
    return await wsl2Sandbox.execute(command, { timeout });
  }
  if (!vmManager) return { exitCode: -1, stdout: "", stderr: "VM not initialized" };
  return await vmManager.execute(command, timeout);
});

ipcMain.handle("vm-pause", async () => {
  return await vmManager?.pauseSandbox() ?? false;
});

ipcMain.handle("vm-resume", async () => {
  return await vmManager?.resumeSandbox() ?? false;
});

ipcMain.handle("vm-save-snapshot", async (_event, name: string) => {
  return await vmManager?.saveSnapshot(name) ?? false;
});

ipcMain.handle("vm-restore-snapshot", async (_event, name: string) => {
  return await vmManager?.restoreSnapshot(name) ?? false;
});

ipcMain.handle("vm-list-snapshots", async () => {
  return await vmManager?.listSnapshots() ?? [];
});

ipcMain.handle("vm-delete-snapshot", async (_event, name: string) => {
  return await vmManager?.deleteSnapshot(name) ?? false;
});

ipcMain.handle("vm-default-config", async () => {
  if (!vmManager) return {};
  return await vmManager.getDefaultConfig();
});

ipcMain.handle("wsl2-detect", async () => {
  if (process.platform !== "win32") return null;
  const detector = new WSL2Detector();
  wsl2Support = await detector.detect();
  mainWindow?.webContents.send("wsl2-support", wsl2Support);
  return wsl2Support;
});

ipcMain.handle("wsl2-install", async () => {
  if (process.platform !== "win32") return { success: false, message: "Not Windows" };

  if (!wsl2Wizard) {
    wsl2Wizard = new WSL2SetupWizard();
  }

  wsl2Wizard.on("install-progress", (step: string, message: string) => {
    mainWindow?.webContents.send("wsl2-install-progress", { step, message });
  });

  return await wsl2Wizard.startInstall();
});

ipcMain.handle("wsl2-wizard-detect", async () => {
  if (process.platform !== "win32") return null;

  if (!wsl2Wizard) {
    wsl2Wizard = new WSL2SetupWizard();
  }

  wsl2Wizard.on("status-update", (status: WizardStatus) => {
    mainWindow?.webContents.send("wsl2-wizard-status", status);
  });

  return await wsl2Wizard.startDetection();
});

ipcMain.handle("wsl2-wizard-resume", async () => {
  if (process.platform !== "win32") return null;

  if (!wsl2Wizard) {
    wsl2Wizard = new WSL2SetupWizard();
  }

  return await wsl2Wizard.resumeAfterRestart();
});

ipcMain.handle("wsl2-workspace-setup", async (_event, mode: WorkspaceMode) => {
  if (process.platform !== "win32" || !workspaceMount) return null;
  return await workspaceMount.setup(mode);
});

ipcMain.handle("wsl2-workspace-verify", async () => {
  if (process.platform !== "win32" || !workspaceMount) return null;
  return await workspaceMount.verifyAccess();
});

ipcMain.handle("wsl2-distro-update", async (_event, imagePath: string) => {
  if (process.platform !== "win32" || !distroManager) return null;
  return await distroManager.update(imagePath);
});

ipcMain.handle("wsl2-distro-version", async () => {
  if (process.platform !== "win32" || !distroManager) return null;
  return await distroManager.getCurrentVersion();
});

ipcMain.handle("wsl2-distro-health", async () => {
  if (process.platform !== "win32" || !distroManager) return null;
  return await distroManager.checkHealth();
});

ipcMain.handle("select-directory", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory"],
  });
  if (result.canceled) return null;
  return result.filePaths[0] ?? null;
});

ipcMain.handle("open-in-explorer", (_event, filePath: string) => {
  shell.showItemInFolder(filePath);
});

ipcMain.on("install-update", () => {
  updater?.installUpdate();
});

ipcMain.handle("check-for-updates", async () => {
  await updater?.checkForUpdates();
});

ipcMain.on("console:set-open", (_event, open: boolean) => {
  logger?.setConsoleOpen(open);
});

ipcMain.handle("console:get-recent-logs", (_event, count?: number) => {
  return logger?.getRecentLogs(count) ?? [];
});

ipcMain.handle("console:clear-logs", () => {
  return logger?.clearLogs() ?? false;
});

ipcMain.handle("console:export-logs", async () => {
  const result = await dialog.showSaveDialog({
    defaultPath: `deerflow-logs-${new Date().toISOString().split("T")[0]}.log`,
    filters: [{ name: "Log Files", extensions: ["log"] }],
  });
  if (result.canceled || !result.filePath) return null;
  const success = logger?.exportLogs(result.filePath) ?? false;
  return success ? result.filePath : null;
});

ipcMain.on("open-settings", () => {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.webContents.send("open-settings");
  }
});

ipcMain.handle("get-settings", () => {
  return loadSettings();
});

ipcMain.handle("save-settings", (_event, settings: Record<string, unknown>) => {
  return saveSettingsToFile(settings);
});
