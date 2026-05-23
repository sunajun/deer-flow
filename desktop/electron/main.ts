import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell, dialog } from "electron";
import path from "path";
import { PythonBackendManager } from "./python-backend";

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let backendManager: PythonBackendManager | null = null;
let isQuitting = false;

const PROTOCOL = "deerflow";

function getIconPath(): string {
  return path.join(__dirname, "../assets/icon.png");
}

function createTray(): void {
  const icon = nativeImage.createFromPath(getIconPath());
  tray = new Tray(icon.resize({ width: 16, height: 16 }));
  const contextMenu = Menu.buildFromTemplate([
    { label: "显示窗口", click: () => mainWindow?.show() },
    { type: "separator" },
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

    createTray();
    createMainWindow();

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
  const platform = process.platform;
  if (platform === "darwin") {
    return { type: "virtualization-framework", available: true };
  } else if (platform === "win32") {
    return { type: "wsl2", available: false };
  } else {
    return { type: "kvm", available: false };
  }
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
