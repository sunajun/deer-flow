import { EventEmitter } from "events";
import { WSL2Detector, WSL2Support } from "./wsl2-detector";
import { WSL2Installer, InstallResult, InstallStep } from "./wsl2-installer";
import { detectWindowsVersion, WindowsVersion } from "./windows-version";

export type WizardState =
  | "idle"
  | "detecting"
  | "ready"
  | "installing"
  | "needs_restart"
  | "restart_resuming"
  | "completed"
  | "error"
  | "skipped";

export interface WizardStatus {
  state: WizardState;
  wsl2Support: WSL2Support | null;
  windowsVersion: WindowsVersion | null;
  installStep: InstallStep | null;
  installMessage: string | null;
  errorMessage: string | null;
  canAutoInstall: boolean;
  buttonText: string;
  showSkip: boolean;
}

export class WSL2SetupWizard extends EventEmitter {
  private detector = new WSL2Detector();
  private installer = new WSL2Installer();
  private _state: WizardState = "idle";
  private _wsl2Support: WSL2Support | null = null;
  private _windowsVersion: WindowsVersion | null = null;
  private _installStep: InstallStep | null = null;
  private _installMessage: string | null = null;
  private _errorMessage: string | null = null;

  get state(): WizardState {
    return this._state;
  }

  get status(): WizardStatus {
    const canAutoInstall =
      this._wsl2Support?.canAutoInstall ??
      (this._windowsVersion?.isWSL2Supported ?? false);

    const buttonText = this.getButtonText();

    return {
      state: this._state,
      wsl2Support: this._wsl2Support,
      windowsVersion: this._windowsVersion,
      installStep: this._installStep,
      installMessage: this._installMessage,
      errorMessage: this._errorMessage,
      canAutoInstall,
      buttonText,
      showSkip: true,
    };
  }

  private getButtonText(): string {
    if (!this._windowsVersion) return "检测中...";

    if (this._wsl2Support?.wslInstalled && this._wsl2Support?.wsl2Default) {
      return "WSL2 已就绪";
    }

    if (this._windowsVersion.isWindows11) {
      return "一键启用 WSL2（推荐）";
    }

    return "启用 WSL2（需要重启）";
  }

  private setState(state: WizardState): void {
    this._state = state;
    this.emit("state-change", state);
    this.emit("status-update", this.status);
  }

  async startDetection(): Promise<WizardStatus> {
    this.setState("detecting");

    try {
      this._windowsVersion = await detectWindowsVersion();
      this._wsl2Support = await this.detector.detect();

      if (
        this._wsl2Support.wslInstalled &&
        this._wsl2Support.wsl2Default &&
        this._wsl2Support.deerFlowDistroInstalled
      ) {
        this.setState("completed");
      } else if (
        this._wsl2Support.wslInstalled &&
        this._wsl2Support.wsl2Default
      ) {
        this.setState("ready");
      } else if (this._wsl2Support.canAutoInstall) {
        this.setState("ready");
      } else if (this._wsl2Support.wslInstalled && !this._wsl2Support.wsl2Default) {
        this.setState("ready");
      } else {
        this.setState("ready");
      }
    } catch (err) {
      this._errorMessage =
        err instanceof Error ? err.message : "检测 WSL2 状态失败";
      this.setState("error");
    }

    return this.status;
  }

  async startInstall(): Promise<InstallResult> {
    if (this._state !== "ready") {
      return {
        success: false,
        needsRestart: false,
        message: "当前状态不允许安装",
        error: `当前状态: ${this._state}`,
      };
    }

    this.setState("installing");

    this.installer.on(
      "progress",
      (step: InstallStep, message: string) => {
        this._installStep = step;
        this._installMessage = message;
        this.emit("install-progress", step, message);
        this.emit("status-update", this.status);
      }
    );

    try {
      const result = await this.installer.install();

      if (result.success) {
        if (result.needsRestart) {
          await this.installer.setRestartMark(
            JSON.stringify({ step: "sandbox", wsl2Installed: true })
          );
          this.setState("needs_restart");
        } else {
          this.setState("completed");
        }
      } else {
        this._errorMessage = result.error || result.message;
        this.setState("error");
      }

      return result;
    } catch (err) {
      this._errorMessage =
        err instanceof Error ? err.message : "安装过程发生未知错误";
      this.setState("error");
      return {
        success: false,
        needsRestart: false,
        message: this._errorMessage,
        error: this._errorMessage,
      };
    }
  }

  async resumeAfterRestart(): Promise<WizardStatus> {
    this.setState("restart_resuming");

    try {
      const wizardState = await this.installer.checkResumeAfterRestart();

      if (!wizardState) {
        return this.startDetection();
      }

      this._windowsVersion = await detectWindowsVersion();
      this._wsl2Support = await this.detector.detect();

      if (this._wsl2Support.wslInstalled && this._wsl2Support.wsl2Default) {
        this.setState("completed");
      } else {
        this._errorMessage = "重启后 WSL2 未安装成功，请重试";
        this.setState("error");
      }
    } catch (err) {
      this._errorMessage =
        err instanceof Error ? err.message : "恢复安装状态失败";
      this.setState("error");
    }

    return this.status;
  }

  skip(): void {
    this.setState("skipped");
  }

  retry(): Promise<WizardStatus> {
    this._errorMessage = null;
    this._installStep = null;
    this._installMessage = null;
    return this.startDetection();
  }
}
