import { app, Tray, Menu, nativeImage, BrowserWindow, Notification } from "electron";
import path from "path";

export type TrayStatus = "running" | "stopped" | "error" | "updating";

interface TrayDependencies {
  showMainWindow: () => void;
  restartBackend: () => void;
  pauseSandbox: () => Promise<boolean>;
  resumeSandbox: () => Promise<boolean>;
  checkForUpdates: () => void;
  openSettings: () => void;
  quitApp: () => void;
  getBackendStatus: () => string;
  getSandboxType: () => string;
  getSandboxState: () => string;
  getAppVersion: () => string;
}

export class DeerFlowTray {
  private tray: Tray | null = null;
  private status: TrayStatus = "stopped";
  private updateAvailable = false;
  private deps: TrayDependencies;

  constructor(deps: TrayDependencies) {
    this.deps = deps;
  }

  private getIconPath(name: string): string {
    return path.join(__dirname, "../assets", name);
  }

  private getTrayIcon(): Electron.NativeImage {
    if (process.platform === "darwin") {
      const templatePath = this.getIconPath("tray-iconTemplate.png");
      try {
        return nativeImage.createFromPath(templatePath);
      } catch {
        return nativeImage.createFromPath(this.getIconPath("tray-icon.png")).resize({ width: 16, height: 16 });
      }
    }

    const iconName = this.status === "running"
      ? "tray-icon.png"
      : this.status === "error"
        ? "tray-icon-error.png"
        : this.status === "updating"
          ? "tray-icon-update.png"
          : "tray-icon.png";

    try {
      return nativeImage.createFromPath(this.getIconPath(iconName)).resize({ width: 16, height: 16 });
    } catch {
      return nativeImage.createFromPath(this.getIconPath("tray-icon.png")).resize({ width: 16, height: 16 });
    }
  }

  create(): void {
    const icon = this.getTrayIcon();
    this.tray = new Tray(icon);

    this.tray.setToolTip("DeerFlow");
    this.rebuildMenu();

    if (process.platform === "darwin" || process.platform === "linux") {
      this.tray.on("click", () => {
        this.deps.showMainWindow();
      });
    }

    if (process.platform === "win32") {
      this.tray.on("double-click", () => {
        this.deps.showMainWindow();
      });
    }
  }

  setStatus(status: TrayStatus): void {
    this.status = status;
    if (this.tray) {
      this.tray.setImage(this.getTrayIcon());
      this.rebuildMenu();
    }
  }

  setUpdateAvailable(available: boolean): void {
    this.updateAvailable = available;
    if (this.tray) {
      this.rebuildMenu();
    }
  }

  private rebuildMenu(): void {
    if (!this.tray) return;

    const version = this.deps.getAppVersion();
    const sandboxType = this.deps.getSandboxType();
    const sandboxState = this.deps.getSandboxState();

    const statusLabel = this.status === "running"
      ? "🟢 运行中"
      : this.status === "error"
        ? "🔴 已停止"
        : "⚪ 已停止";

    const sandboxLabel = sandboxType === "virtualization-framework"
      ? "macOS VM"
      : sandboxType === "wsl2"
        ? "WSL2"
        : sandboxType === "firecracker"
        ? "Firecracker"
        : "本地模式";

    const sandboxStateLabel = sandboxState === "running"
      ? "运行中"
      : sandboxState === "paused"
        ? "已暂停"
        : sandboxState === "error"
          ? "错误"
          : "未启动";

    const isPaused = sandboxState === "paused";
    const isRunning = sandboxState === "running";

    const template: Electron.MenuItemConstructorOptions[] = [
      { label: `DeerFlow v${version}`, enabled: false },
      { type: "separator" },
      { label: statusLabel, enabled: false },
      { type: "separator" },
      { label: "打开主窗口", click: () => this.deps.showMainWindow() },
      {
        label: "沙箱状态",
        submenu: [
          { label: `${sandboxLabel} - ${sandboxStateLabel}`, enabled: false },
          { type: "separator" as const },
          ...(isRunning ? [{ label: "暂停沙箱", click: () => this.deps.pauseSandbox() } as Electron.MenuItemConstructorOptions] : []),
          ...(isPaused ? [{ label: "恢复沙箱", click: () => this.deps.resumeSandbox() } as Electron.MenuItemConstructorOptions] : []),
        ],
      },
      { type: "separator" },
      { label: "重启后端", click: () => this.deps.restartBackend() },
      { type: "separator" },
      ...(this.updateAvailable
        ? [
            { label: "📥 更新可用，点击安装", click: () => this.deps.checkForUpdates() } as Electron.MenuItemConstructorOptions,
            { type: "separator" as const },
          ]
        : [
            { label: "检查更新...", click: () => this.deps.checkForUpdates() } as Electron.MenuItemConstructorOptions,
            { type: "separator" as const },
          ]),
      { label: "偏好设置...", click: () => this.deps.openSettings() },
      { type: "separator" },
      { label: "退出 DeerFlow", click: () => this.deps.quitApp() },
    ];

    const contextMenu = Menu.buildFromTemplate(template);
    this.tray.setContextMenu(contextMenu);
  }

  showNotification(title: string, body: string, onClick?: () => void): void {
    if (Notification.isSupported()) {
      const notification = new Notification({ title, body, silent: false });
      if (onClick) {
        notification.on("click", onClick);
      }
      notification.show();
    }
  }

  notifyBackendReady(): void {
    this.showNotification("DeerFlow", "DeerFlow 已就绪", () => this.deps.showMainWindow());
  }

  notifyBackendError(): void {
    this.showNotification("DeerFlow", "后端异常，点击查看", () => this.deps.showMainWindow());
  }

  notifyUpdateAvailable(version: string): void {
    this.showNotification("DeerFlow", `新版本 ${version} 可用`, () => this.deps.checkForUpdates());
  }

  notifyUpdateDownloaded(): void {
    this.showNotification("DeerFlow", "点击重启安装更新", () => this.deps.checkForUpdates());
  }

  destroy(): void {
    if (this.tray) {
      this.tray.destroy();
      this.tray = null;
    }
  }
}
