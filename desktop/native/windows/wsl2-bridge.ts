import { EventEmitter } from "events";
import * as path from "path";
import * as os from "os";
import * as fs from "fs";
import { runCommand, CommandOutput, getShortPath } from "./windows-version";

export interface ExecuteOptions {
  cwd?: string;
  env?: Record<string, string>;
  timeout?: number;
}

export interface CommandResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  error?: string;
}

export type WSL2ErrorCode =
  | "WSL_NOT_INSTALLED"
  | "WSL1_NOT_WSL2"
  | "DISK_SPACE_INSUFFICIENT"
  | "IMAGE_CORRUPT"
  | "WSL_SERVICE_CRASH"
  | "HYPERV_CONFLICT"
  | "ENTERPRISE_POLICY"
  | "CHINESE_PATH"
  | "NEEDS_RESTART_WIN10"
  | "WSL_INSTALL_NETWORK_WIN11"
  | "COMMAND_TIMEOUT"
  | "UNKNOWN";

export class WSL2Error extends Error {
  code: WSL2ErrorCode;
  recoverable: boolean;
  suggestion: string;

  constructor(code: WSL2ErrorCode, message: string, recoverable: boolean, suggestion: string) {
    super(message);
    this.name = "WSL2Error";
    this.code = code;
    this.recoverable = recoverable;
    this.suggestion = suggestion;
  }
}

function classifyError(err: unknown): WSL2Error {
  const message = err instanceof Error ? err.message : String(err);
  const lowerMessage = message.toLowerCase();

  if (lowerMessage.includes("wsl") && (lowerMessage.includes("not found") || lowerMessage.includes("not recognized") || lowerMessage.includes("找不到"))) {
    return new WSL2Error(
      "WSL_NOT_INSTALLED",
      "WSL 未安装",
      true,
      "请在启动向导中点击「一键启用 WSL2」，或降级到本地模式运行"
    );
  }

  if (lowerMessage.includes("wsl1") || (lowerMessage.includes("默认版本") && lowerMessage.includes("1"))) {
    return new WSL2Error(
      "WSL1_NOT_WSL2",
      "WSL 默认版本为 WSL1，需要升级到 WSL2",
      true,
      "正在自动升级到 WSL2，请稍候"
    );
  }

  if (lowerMessage.includes("磁盘空间不足") || lowerMessage.includes("disk space") || lowerMessage.includes("not enough space")) {
    return new WSL2Error(
      "DISK_SPACE_INSUFFICIENT",
      "磁盘空间不足，无法导入发行版",
      true,
      "请释放至少 2GB 磁盘空间后重试"
    );
  }

  if (lowerMessage.includes("损坏") || lowerMessage.includes("corrupt") || lowerMessage.includes("checksum")) {
    return new WSL2Error(
      "IMAGE_CORRUPT",
      "发行版镜像文件损坏",
      true,
      "请重新下载 deerflow-rootfs.tar.gz，或校验文件 SHA256"
    );
  }

  if (lowerMessage.includes("超时") || lowerMessage.includes("timed out") || lowerMessage.includes("timeout") || lowerMessage.includes("无响应")) {
    return new WSL2Error(
      "WSL_SERVICE_CRASH",
      "WSL 服务无响应，可能已崩溃",
      true,
      "正在尝试重启 WSL 服务，请稍候"
    );
  }

  if (lowerMessage.includes("hyperv") || lowerMessage.includes("hyper-v") || lowerMessage.includes("virtualbox") || lowerMessage.includes("vmware")) {
    return new WSL2Error(
      "HYPERV_CONFLICT",
      "虚拟化软件冲突",
      true,
      "请关闭 VMware/VirtualBox 后重试；VirtualBox 6.1+ 与 WSL2 兼容"
    );
  }

  if (lowerMessage.includes("组策略") || lowerMessage.includes("group policy") || lowerMessage.includes("enterprise") || lowerMessage.includes("企业")) {
    return new WSL2Error(
      "ENTERPRISE_POLICY",
      "企业环境组策略禁止安装 WSL",
      false,
      "请联系 IT 管理员开放 WSL 安装权限，或降级到本地模式运行"
    );
  }

  if (lowerMessage.includes("中文") || lowerMessage.includes("unicode") || (/[\u4e00-\u9fff]/.test(message) && lowerMessage.includes("路径"))) {
    return new WSL2Error(
      "CHINESE_PATH",
      "Windows 用户名含中文字符导致路径异常",
      true,
      "正在使用 8.3 短路径名替代，或切换到 WSL2 原生文件系统"
    );
  }

  if (lowerMessage.includes("需要重启") || lowerMessage.includes("reboot") || lowerMessage.includes("restart required")) {
    return new WSL2Error(
      "NEEDS_RESTART_WIN10",
      "Windows 功能已启用，需要重启计算机",
      true,
      "请重启计算机后继续配置，安装进度已保存"
    );
  }

  if (lowerMessage.includes("网络") && (lowerMessage.includes("wsl --install") || lowerMessage.includes("下载"))) {
    return new WSL2Error(
      "WSL_INSTALL_NETWORK_WIN11",
      "WSL 安装下载超时",
      true,
      "请检查网络连接，或使用离线安装包；也可尝试 dism 方式安装"
    );
  }

  return new WSL2Error(
    "UNKNOWN",
    message,
    true,
    "请重试，或降级到本地模式运行"
  );
}

type SandboxState = "stopped" | "starting" | "running" | "error";

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;

export class WSL2Sandbox extends EventEmitter {
  private distroName = "DeerFlow";
  private initialized = false;
  private _state: SandboxState = "stopped";

  get state(): SandboxState {
    return this._state;
  }

  get name(): string {
    return this.distroName;
  }

  private setState(state: SandboxState): void {
    this._state = state;
    this.emit("state-change", state);
  }

  async init(imagePath?: string): Promise<void> {
    const distroInstalled = await this.isDistroInstalled();
    if (distroInstalled) {
      this.initialized = true;
      return;
    }

    let tarPath =
      imagePath ||
      path.join(
        process.resourcesPath || path.resolve(__dirname, "../../resources"),
        "vm-images",
        "deerflow-rootfs.tar.gz"
      );

    if (!fs.existsSync(tarPath)) {
      throw new WSL2Error(
        "IMAGE_CORRUPT",
        `发行版镜像文件不存在: ${tarPath}`,
        true,
        "请确认 deerflow-rootfs.tar.gz 已放置在正确位置"
      );
    }

    const installPath = this.getInstallPath();
    if (!fs.existsSync(installPath)) {
      fs.mkdirSync(installPath, { recursive: true });
    }

    const diskInfo = this.checkDiskSpace(installPath);
    if (diskInfo < 2) {
      throw new WSL2Error(
        "DISK_SPACE_INSUFFICIENT",
        `磁盘空间不足，至少需要 2GB，当前可用 ${diskInfo.toFixed(1)}GB`,
        true,
        "请释放磁盘空间后重试"
      );
    }

    try {
      const hasChinese = /[\u4e00-\u9fff]/.test(tarPath) || /[\u4e00-\u9fff]/.test(installPath);
      if (hasChinese) {
        const shortTarPath = await getShortPath(tarPath);
        if (shortTarPath !== tarPath) tarPath = shortTarPath;
      }
    } catch {}

    const result = await runCommand(
      `wsl --import ${this.distroName} "${installPath}" "${tarPath}" --version 2`,
      300000
    );

    if (result.exitCode !== 0) {
      throw this.classifyImportError(result);
    }

    await this.configureDistro();

    this.initialized = true;
  }

  async execute(command: string, options?: ExecuteOptions): Promise<CommandResult> {
    if (!this.initialized) {
      return {
        exitCode: -1,
        stdout: "",
        stderr: "WSL2 沙箱未初始化",
        error: "WSL2 沙箱未初始化",
      };
    }

    const cwd = options?.cwd ? `--cd "${options.cwd}"` : "";
    const envArgs = options?.env
      ? Object.entries(options.env)
          .map(([k, v]) => `--env ${k}="${v}"`)
          .join(" ")
      : "";
    const timeout = options?.timeout || 300;

    const escapedCommand = command.replace(/"/g, '\\"');
    const cmd = `wsl -d ${this.distroName} ${cwd} ${envArgs} -- bash -c "${escapedCommand}"`;

    try {
      const result = await runCommand(cmd, timeout * 1000);

      if (result.exitCode === -1 && result.stderr === "Command timed out") {
        return await this.handleTimeout(command, options);
      }

      return {
        exitCode: result.exitCode,
        stdout: result.stdout,
        stderr: result.stderr,
      };
    } catch (err) {
      const wsl2Error = classifyError(err);
      return {
        exitCode: -1,
        stdout: "",
        stderr: wsl2Error.suggestion,
        error: wsl2Error.message,
      };
    }
  }

  async executeWithRetry(command: string, options?: ExecuteOptions, retries: number = MAX_RETRIES): Promise<CommandResult> {
    let lastResult: CommandResult | null = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
      lastResult = await this.execute(command, options);

      if (lastResult.exitCode === 0) {
        return lastResult;
      }

      const wsl2Error = classifyError(new Error(lastResult.error || lastResult.stderr));

      if (!wsl2Error.recoverable) {
        return lastResult;
      }

      if (wsl2Error.code === "WSL_SERVICE_CRASH") {
        const recovered = await this.recoverWslService();
        if (!recovered) break;
      }

      if (wsl2Error.code === "WSL1_NOT_WSL2") {
        await this.upgradeToWSL2();
      }

      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
      }
    }

    return lastResult!;
  }

  async start(): Promise<void> {
    if (!this.initialized) {
      throw new WSL2Error(
        "WSL_NOT_INSTALLED",
        "WSL2 沙箱未初始化，请先调用 init()",
        true,
        "请先初始化沙箱"
      );
    }

    this.setState("starting");

    try {
      const result = await this.executeWithRetry("echo ready", { timeout: 30 });

      if (result.exitCode === 0 && result.stdout.trim().includes("ready")) {
        this.setState("running");
      } else {
        this.setState("error");
        const wsl2Error = classifyError(new Error(result.stderr || result.stdout));
        throw wsl2Error;
      }
    } catch (err) {
      this.setState("error");
      if (err instanceof WSL2Error) throw err;
      throw classifyError(err);
    }
  }

  async stop(): Promise<void> {
    try {
      const result = await runCommand(`wsl -t ${this.distroName}`, 30000);
      if (result.exitCode !== 0) {
        throw classifyError(new Error(result.stderr));
      }
      this.setState("stopped");
    } catch (err) {
      if (err instanceof WSL2Error) throw err;
      throw classifyError(err);
    }
  }

  async isRunning(): Promise<boolean> {
    const result = await runCommand("wsl -l -v", 10000);
    if (result.exitCode !== 0) return false;

    const lines = result.stdout.split("\n");
    for (const line of lines) {
      if (line.includes(this.distroName)) {
        return line.includes("Running") || line.includes("运行中");
      }
    }

    return false;
  }

  async dispose(): Promise<void> {
    try {
      const result = await runCommand(
        `wsl --unregister ${this.distroName}`,
        30000
      );

      if (result.exitCode !== 0) {
        throw classifyError(new Error(result.stderr));
      }

      const installPath = this.getInstallPath();
      try {
        if (fs.existsSync(installPath)) {
          fs.rmSync(installPath, { recursive: true, force: true });
        }
      } catch {}
    } catch (err) {
      if (err instanceof WSL2Error) throw err;
      throw classifyError(err);
    }

    this.initialized = false;
    this.setState("stopped");
  }

  private async handleTimeout(command: string, options?: ExecuteOptions): Promise<CommandResult> {
    const recovered = await this.recoverWslService();
    if (recovered) {
      const retryResult = await this.execute(command, options);
      if (retryResult.exitCode === 0) {
        return retryResult;
      }
    }

    return {
      exitCode: -1,
      stdout: "",
      stderr: "WSL 服务无响应，已尝试自动恢复",
      error: "命令执行超时，WSL 服务可能已崩溃",
    };
  }

  private async recoverWslService(): Promise<boolean> {
    try {
      await runCommand("wsl --shutdown", 30000);
      await new Promise((resolve) => setTimeout(resolve, 3000));
      return true;
    } catch {
      return false;
    }
  }

  private async upgradeToWSL2(): Promise<void> {
    await runCommand("wsl --set-default-version 2", 30000);
  }

  private classifyImportError(result: CommandOutput): WSL2Error {
    const stderr = result.stderr.toLowerCase();
    const stdout = result.stdout.toLowerCase();

    if (stderr.includes("磁盘空间不足") || stderr.includes("disk space") || stdout.includes("磁盘空间不足")) {
      return new WSL2Error(
        "DISK_SPACE_INSUFFICIENT",
        "磁盘空间不足，无法导入发行版",
        true,
        "请释放至少 2GB 磁盘空间后重试"
      );
    }

    if (stderr.includes("损坏") || stderr.includes("corrupt") || stderr.includes("invalid")) {
      return new WSL2Error(
        "IMAGE_CORRUPT",
        "发行版镜像文件损坏",
        true,
        "请重新下载 deerflow-rootfs.tar.gz，或校验文件 SHA256"
      );
    }

    if (stderr.includes("组策略") || stderr.includes("group policy")) {
      return new WSL2Error(
        "ENTERPRISE_POLICY",
        "企业环境组策略禁止安装 WSL",
        false,
        "请联系 IT 管理员开放 WSL 安装权限，或降级到本地模式运行"
      );
    }

    if (stderr.includes("hyper-v") || stderr.includes("hyperv")) {
      return new WSL2Error(
        "HYPERV_CONFLICT",
        "Hyper-V 相关错误",
        true,
        "请确认 Hyper-V 和虚拟机平台功能已启用；如与 VMware/VirtualBox 冲突，请升级 VirtualBox 到 6.1+"
      );
    }

    if (stderr.includes("wsl") && (stderr.includes("not found") || stderr.includes("not recognized"))) {
      return new WSL2Error(
        "WSL_NOT_INSTALLED",
        "WSL 未安装",
        true,
        "请在启动向导中点击「一键启用 WSL2」，或降级到本地模式运行"
      );
    }

    return new WSL2Error(
      "UNKNOWN",
      `发行版导入失败: ${result.stderr || result.stdout}`,
      true,
      "请重试，或查看日志获取详细信息"
    );
  }

  private async isDistroInstalled(): Promise<boolean> {
    const result = await runCommand("wsl -l -v", 10000);
    if (result.exitCode !== 0) return false;

    return result.stdout.includes(this.distroName);
  }

  private async configureDistro(): Promise<void> {
    const wslConf = `[user]
default=sandbox

[automount]
enabled = true
options = "metadata,umask=22,fmask=11"

[interop]
enabled = true
appendWindowsPath = false
`;

    const tmpConfPath = path.join(os.tmpdir(), "deerflow-wsl.conf");
    fs.writeFileSync(tmpConfPath, wslConf, "utf-8");

    const wslSourcePath = this.windowsPathToWsl(tmpConfPath);
    await this.execute(`cp ${wslSourcePath} /etc/wsl.conf`, { timeout: 10 });

    try {
      fs.unlinkSync(tmpConfPath);
    } catch {}

    await this.execute("useradd -m -s /bin/bash sandbox 2>/dev/null || true", {
      timeout: 10,
    });
    await this.execute("usermod -aG sudo sandbox 2>/dev/null || true", {
      timeout: 10,
    });
  }

  private windowsPathToWsl(windowsPath: string): string {
    const normalized = windowsPath.replace(/\\/g, "/");
    const match = normalized.match(/^([A-Za-z]):\/(.*)/);
    if (match) {
      return `/mnt/${match[1].toLowerCase()}/${match[2]}`;
    }
    return normalized;
  }

  private getInstallPath(): string {
    const localAppData =
      process.env.LOCALAPPDATA ||
      path.join(os.homedir(), "AppData", "Local");
    return path.join(localAppData, "DeerFlow", "wsl-distro");
  }

  private checkDiskSpace(dirPath: string): number {
    try {
      const result = runCommandSync(
        `wmic logicaldisk where "DeviceID='${path.parse(dirPath).root.replace("\\", "")}'" get FreeSpace /value`
      );
      const match = result.match(/FreeSpace=(\d+)/);
      if (match) {
        return parseInt(match[1], 10) / (1024 * 1024 * 1024);
      }
    } catch {}
    return 100;
  }
}

function runCommandSync(command: string): string {
  const { execSync } = require("child_process");
  try {
    return execSync(command, { encoding: "utf-8", timeout: 10000 });
  } catch {
    return "";
  }
}
