import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell, dialog } from "electron";
import path from "path";
import { PythonBackendManager } from "./python-backend";
import { VMSandboxManager, VirtualizationSupport, VMConfig, CommandResult, SnapshotInfo } from "./vm-manager";

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let backendManager: PythonBackendManager | null = null;
let vmManager: VMSandboxManager | null = null;
let vmSupport: VirtualizationSupport | null = null;
let isQuitting = false;

const PROTOCOL = "deerflow";

function getIconPath(): string {
  return path.join(__dirname, "../assets/icon.png");
}

function createTray(): void {
  const icon = nativeImage.createFromPath(getIconPath());
  tray = new Tray(icon.resize({ width: 16, height: 16 }));

  const vmMenuItems = vmSupport?.isSupported
    ? [
        { label: "重启 VM 沙箱", click: () => restartVMSandbox() },
        { type: "separator" as const },
      ]
    : [];

  const contextMenu = Menu.buildFromTemplate([
    { label: "显示窗口", click: () => mainWindow?.show() },
    { type: "separator" },
    ...vmMenuItems,
    { label: "重启后端", click: () => backendManager?.restart() },
    { type: "separator" },
    {
      label: "退出",
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);
  tray.setToolTip("DeerFlow");
  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => mainWindow?.show());
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

async function initVMSandbox(): Promise<void> {
  if (process.platform !== "darwin") return;

  vmManager = new VMSandboxManager();

  vmManager.on("state-change", (state: string) => {
    mainWindow?.webContents.send("vm-state", state);
  });

  try {
    vmSupport = await vmManager.detectSupport();
    mainWindow?.webContents.send("vm-support", vmSupport);

    if (!vmSupport.isSupported) {
      console.log("[VM Sandbox] Not supported:", vmSupport.reason);
      return;
    }

    console.log("[VM Sandbox] Virtualization supported:", vmSupport.chipArchitecture);
  } catch (err) {
    console.error("[VM Sandbox] Detection failed:", err);
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
      console.log("[VM Sandbox] Started successfully, id:", id);
      await vmManager.saveSnapshot("boot", id);
    }

    return started;
  } catch (err) {
    console.error("[VM Sandbox] Start failed:", err);
    mainWindow?.webContents.send("vm-state", "error");
    return false;
  }
}

async function stopVMSandbox(): Promise<void> {
  if (!vmManager) return;

  try {
    await vmManager.stopSandbox();
    console.log("[VM Sandbox] Stopped");
  } catch (err) {
    console.error("[VM Sandbox] Stop failed:", err);
  }
}

async function restartVMSandbox(): Promise<void> {
  await stopVMSandbox();
  await startVMSandbox();
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

    createMainWindow();

    await initVMSandbox();
    createTray();

    backendManager = new PythonBackendManager();

    backendManager.on("status", (status: string) => {
      mainWindow?.webContents.send("backend-status", status);
    });

    backendManager.on("port", (port: number) => {
      mainWindow?.webContents.send("backend-port", port);
    });

    try {
      await backendManager.start();
    } catch (err) {
      console.error("Failed to start Python backend:", err);
      mainWindow?.webContents.send("backend-status", "error");
    }
  });

  app.on("before-quit", async () => {
    isQuitting = true;
    await stopVMSandbox();
    if (backendManager) {
      await backendManager.stop();
    }
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
  } else if (process.platform === "win32") {
    return { type: "wsl2", available: false };
  } else {
    return { type: "kvm", available: false };
  }
});

ipcMain.handle("vm-start", async (_event, config?: VMConfig) => {
  return await startVMSandbox(config);
});

ipcMain.handle("vm-stop", async () => {
  await stopVMSandbox();
  return true;
});

ipcMain.handle("vm-execute", async (_event, command: string, timeout?: number) => {
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
