import {
  WindowsVersion,
  CommandOutput,
  runCommand,
  detectWindowsVersion,
  isAdmin,
} from "./windows-version";

export interface WSL2Support {
  wslInstalled: boolean;
  wsl2Default: boolean;
  hyperVEnabled: boolean;
  virtualizationEnabled: boolean;
  deerFlowDistroInstalled: boolean;
  distroState: "Running" | "Stopped" | "none";
  windowsVersion: WindowsVersion;
  issues: string[];
  canAutoInstall: boolean;
  installMethod: "wsl_install" | "dism" | "manual";
}

export class WSL2Detector {
  async detect(): Promise<WSL2Support> {
    const windowsVersion = await detectWindowsVersion();
    const issues: string[] = [];

    if (!windowsVersion.isWSL2Supported) {
      issues.push(
        `当前 Windows 版本 (Build ${windowsVersion.build}) 不支持 WSL2，需要 Build 19041 或更高版本`
      );
      return {
        wslInstalled: false,
        wsl2Default: false,
        hyperVEnabled: false,
        virtualizationEnabled: false,
        deerFlowDistroInstalled: false,
        distroState: "none",
        windowsVersion,
        issues,
        canAutoInstall: false,
        installMethod: "manual",
      };
    }

    const wslInstalled = await this.checkWSLInstalled();
    const wsl2Default = wslInstalled ? await this.checkWSL2Default() : false;
    const virtualizationEnabled = await this.checkVirtualization();
    const hyperVEnabled = await this.checkHyperV();
    const { installed, state } = await this.checkDeerFlowDistro();

    if (!wslInstalled) {
      issues.push("WSL 未安装");
    }
    if (!wsl2Default && wslInstalled) {
      issues.push("WSL 默认版本不是 WSL2");
    }
    if (!virtualizationEnabled) {
      issues.push("BIOS 虚拟化 (VT-x/AMD-V) 未开启，请在 BIOS 中启用");
    }
    if (!hyperVEnabled && wslInstalled) {
      issues.push("Hyper-V 未启用");
    }

    const canAutoInstall =
      virtualizationEnabled &&
      !wslInstalled &&
      windowsVersion.isWSL2Supported;

    return {
      wslInstalled,
      wsl2Default,
      hyperVEnabled,
      virtualizationEnabled,
      deerFlowDistroInstalled: installed,
      distroState: state,
      windowsVersion,
      issues,
      canAutoInstall,
      installMethod: !virtualizationEnabled
        ? "manual"
        : windowsVersion.installMethod,
    };
  }

  private async checkWSLInstalled(): Promise<boolean> {
    const result = await runCommand("wsl --status", 10000);
    if (result.exitCode === 0) return true;

    const versionResult = await runCommand("wsl --version", 10000);
    return versionResult.exitCode === 0;
  }

  private async checkWSL2Default(): Promise<boolean> {
    const result = await runCommand("wsl --status", 10000);
    if (result.exitCode !== 0) return false;

    return (
      result.stdout.includes("默认版本: 2") ||
      result.stdout.includes("Default Version: 2") ||
      result.stdout.includes("默认版本：2")
    );
  }

  private async checkVirtualization(): Promise<boolean> {
    const result = await runCommand(
      "wmic cpu get VirtualizationFirmwareEnabled",
      10000
    );
    if (result.exitCode !== 0) return false;

    return result.stdout.toLowerCase().includes("true");
  }

  private async checkHyperV(): Promise<boolean> {
    const result = await runCommand(
      'dism /online /get-featureinfo /featurename:Microsoft-Hyper-V',
      10000
    );
    if (result.exitCode !== 0) return false;

    return (
      result.stdout.includes("状态: 已启用") ||
      result.stdout.includes("State: Enabled") ||
      result.stdout.includes("状态：已启用")
    );
  }

  private async checkDeerFlowDistro(): Promise<{
    installed: boolean;
    state: "Running" | "Stopped" | "none";
  }> {
    const result = await runCommand("wsl -l -v", 10000);
    if (result.exitCode !== 0) return { installed: false, state: "none" };

    const lines = result.stdout.split("\n");
    for (const line of lines) {
      if (line.includes("DeerFlow")) {
        if (line.includes("Running") || line.includes("运行中")) {
          return { installed: true, state: "Running" };
        }
        return { installed: true, state: "Stopped" };
      }
    }

    return { installed: false, state: "none" };
  }
}
