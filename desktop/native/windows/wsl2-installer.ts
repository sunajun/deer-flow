import { EventEmitter } from "events";
import * as path from "path";
import * as os from "os";
import * as fs from "fs";
import { runCommand, isAdmin, detectWindowsVersion, WindowsVersion } from "./windows-version";
import { WSL2Detector, WSL2Support } from "./wsl2-detector";

export interface InstallResult {
  success: boolean;
  needsRestart: boolean;
  message: string;
  error?: string;
  step?: string;
}

export type InstallStep =
  | "detecting"
  | "requesting_elevation"
  | "enabling_wsl_feature"
  | "enabling_vm_platform"
  | "downloading_kernel"
  | "installing_kernel"
  | "setting_default_version"
  | "completed"
  | "failed";

export class WSL2Installer extends EventEmitter {
  private detector = new WSL2Detector();

  async install(progressCallback?: (step: InstallStep, message: string) => void): Promise<InstallResult> {
    const emit = (step: InstallStep, message: string) => {
      this.emit("progress", step, message);
      progressCallback?.(step, message);
    };

    emit("detecting", "正在检测 Windows 版本...");

    const windowsVersion = await detectWindowsVersion();
    if (!windowsVersion.isWSL2Supported) {
      emit("failed", "当前 Windows 版本不支持 WSL2");
      return {
        success: false,
        needsRestart: false,
        message: "当前 Windows 版本不支持 WSL2",
        error: `需要 Windows 10 Build 19041+，当前 Build ${windowsVersion.build}`,
        step: "detecting",
      };
    }

    emit("requesting_elevation", "正在请求管理员权限...");
    const hasAdmin = await isAdmin();
    if (!hasAdmin) {
      const elevated = await this.requestElevation();
      if (!elevated) {
        emit("failed", "需要管理员权限才能安装 WSL2");
        return {
          success: false,
          needsRestart: false,
          message: "需要管理员权限才能安装 WSL2",
          error: "UAC 提权被拒绝",
          step: "requesting_elevation",
        };
      }
    }

    if (windowsVersion.isWindows11) {
      return this.installWSL2Win11(emit);
    } else {
      return this.installWSL2Win10(emit);
    }
  }

  private async installWSL2Win11(
    emit: (step: InstallStep, message: string) => void
  ): Promise<InstallResult> {
    emit("enabling_wsl_feature", "正在通过 wsl --install 安装 WSL2...");

    const installResult = await runCommand(
      "wsl --install --no-distribution",
      300000
    );

    if (installResult.exitCode !== 0) {
      const isNetworkError =
        installResult.stderr.includes("网络") ||
        installResult.stderr.includes("network") ||
        installResult.stderr.includes("超时") ||
        installResult.stderr.includes("timeout");

      if (isNetworkError) {
        emit("failed", "网络错误，尝试使用 dism 方式安装...");
        return this.installWSL2Win10(emit);
      }

      emit("failed", "WSL2 安装失败");
      return {
        success: false,
        needsRestart: false,
        message: "WSL2 安装失败",
        error: installResult.stderr || `退出码: ${installResult.exitCode}`,
        step: "enabling_wsl_feature",
      };
    }

    emit("setting_default_version", "正在设置 WSL2 为默认版本...");
    await runCommand("wsl --set-default-version 2", 30000);

    emit("completed", "WSL2 安装完成，需要重启计算机");
    return {
      success: true,
      needsRestart: true,
      message: "WSL2 已安装，需要重启计算机",
    };
  }

  private async installWSL2Win10(
    emit: (step: InstallStep, message: string) => void
  ): Promise<InstallResult> {
    emit("enabling_wsl_feature", "正在启用适用于 Linux 的 Windows 子系统...");
    const wslFeature = await runCommand(
      "dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart",
      120000
    );

    if (wslFeature.exitCode !== 0) {
      emit("failed", "启用 WSL 功能失败");
      return {
        success: false,
        needsRestart: false,
        message: "启用 WSL 功能失败",
        error: wslFeature.stderr,
        step: "enabling_wsl_feature",
      };
    }

    emit("enabling_vm_platform", "正在启用虚拟机平台...");
    const vmFeature = await runCommand(
      "dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart",
      120000
    );

    if (vmFeature.exitCode !== 0) {
      emit("failed", "启用虚拟机平台失败");
      return {
        success: false,
        needsRestart: false,
        message: "启用虚拟机平台失败",
        error: vmFeature.stderr,
        step: "enabling_vm_platform",
      };
    }

    emit("downloading_kernel", "正在下载 WSL2 Linux 内核更新包...");
    const wslUpdateUrl =
      "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi";
    const msiPath = path.join(os.tmpdir(), "wsl_update_x64.msi");

    const downloadResult = await this.downloadFile(wslUpdateUrl, msiPath);
    if (!downloadResult) {
      emit("failed", "下载 WSL2 内核更新包失败");
      return {
        success: false,
        needsRestart: true,
        message: "下载 WSL2 内核更新包失败，但 Windows 功能已启用，重启后可手动安装内核",
        error: "下载失败",
        step: "downloading_kernel",
      };
    }

    emit("installing_kernel", "正在安装 WSL2 Linux 内核...");
    const msiResult = await runCommand(
      `msiexec /i "${msiPath}" /quiet`,
      120000
    );

    try {
      fs.unlinkSync(msiPath);
    } catch {}

    if (msiResult.exitCode !== 0) {
      emit("failed", "安装 WSL2 内核失败");
      return {
        success: false,
        needsRestart: true,
        message: "安装 WSL2 内核失败，但 Windows 功能已启用，重启后可手动安装",
        error: msiResult.stderr,
        step: "installing_kernel",
      };
    }

    emit("setting_default_version", "正在设置 WSL2 为默认版本...");
    await runCommand("wsl --set-default-version 2", 30000);

    emit("completed", "WSL2 安装完成，需要重启计算机");
    return {
      success: true,
      needsRestart: true,
      message: "WSL2 功能已启用，需要重启计算机",
    };
  }

  private async requestElevation(): Promise<boolean> {
    try {
      const sudoPrompt = require("sudo-prompt");
      return new Promise((resolve) => {
        sudoPrompt.exec(
          'echo "elevated"',
          { name: "DeerFlow" },
          (error: Error | null) => {
            resolve(!error);
          }
        );
      });
    } catch {
      return false;
    }
  }

  private async downloadFile(url: string, destPath: string): Promise<boolean> {
    try {
      const https = await import("https");
      const http = await import("http");
      const client = url.startsWith("https") ? https : http;

      return new Promise((resolve) => {
        const file = fs.createWriteStream(destPath);
        const request = client.get(url, (response) => {
          if (response.statusCode === 301 || response.statusCode === 302) {
            const redirectUrl = response.headers.location;
            if (redirectUrl) {
              file.close();
              try { fs.unlinkSync(destPath); } catch {}
              this.downloadFile(redirectUrl, destPath).then(resolve);
              return;
            }
          }

          if (response.statusCode !== 200) {
            file.close();
            try { fs.unlinkSync(destPath); } catch {}
            resolve(false);
            return;
          }

          response.pipe(file);
          file.on("finish", () => {
            file.close();
            resolve(true);
          });
        });

        request.on("error", () => {
          file.close();
          try { fs.unlinkSync(destPath); } catch {}
          resolve(false);
        });

        request.setTimeout(120000, () => {
          request.destroy();
          file.close();
          try { fs.unlinkSync(destPath); } catch {}
          resolve(false);
        });
      });
    } catch {
      return false;
    }
  }

  async setRestartMark(wizardState?: string): Promise<void> {
    const regKey =
      'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce';
    const appPath = process.execPath;
    const args = wizardState
      ? `--resume-wizard --wizard-state "${wizardState}"`
      : "--resume-wizard";

    await runCommand(
      `reg add "${regKey}" /v DeerFlowResume /t REG_SZ /d "\"${appPath}\" ${args}" /f`,
      10000
    );

    if (wizardState) {
      const statePath = path.join(
        os.homedir(),
        ".deerflow",
        "wizard-state.json"
      );
      const stateDir = path.dirname(statePath);
      if (!fs.existsSync(stateDir)) {
        fs.mkdirSync(stateDir, { recursive: true });
      }
      fs.writeFileSync(statePath, wizardState, "utf-8");
    }
  }

  async checkResumeAfterRestart(): Promise<string | null> {
    const statePath = path.join(
      os.homedir(),
      ".deerflow",
      "wizard-state.json"
    );
    try {
      if (fs.existsSync(statePath)) {
        const state = fs.readFileSync(statePath, "utf-8");
        fs.unlinkSync(statePath);
        return state;
      }
    } catch {}
    return null;
  }
}
