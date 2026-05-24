import * as path from "path";
import * as os from "os";
import * as fs from "fs";
import { runCommand, getShortPath } from "./windows-version";
import { WSL2Sandbox } from "./wsl2-bridge";

export type WorkspaceMode = "wsl_native" | "windows_mount";

export interface WorkspaceConfig {
  mode: WorkspaceMode;
  windowsPath: string;
  wslPath: string;
  description: string;
}

export class PathConverter {
  windowsToWsl(windowsPath: string): string {
    const normalized = windowsPath.replace(/\\/g, "/");
    const match = normalized.match(/^([A-Za-z]):\/(.*)/);
    if (match) {
      const drive = match[1].toLowerCase();
      const rest = match[2];
      return `/mnt/${drive}/${rest}`;
    }
    return normalized;
  }

  wslToWindows(wslPath: string): string {
    const mntMatch = wslPath.match(/^\/mnt\/([a-z])\/(.*)/);
    if (mntMatch) {
      const drive = mntMatch[1].toUpperCase();
      const rest = mntMatch[2].replace(/\//g, "\\");
      return `${drive}:\\${rest}`;
    }
    return `\\\\wsl$\\DeerFlow${wslPath.replace(/\//g, "\\")}`;
  }

  wslNativeToWindows(wslPath: string): string {
    return `\\\\wsl$\\DeerFlow${wslPath.replace(/\//g, "\\")}`;
  }
}

export class WorkspaceMount {
  private sandbox: WSL2Sandbox;
  private pathConverter = new PathConverter();
  private _config: WorkspaceConfig | null = null;

  constructor(sandbox: WSL2Sandbox) {
    this.sandbox = sandbox;
  }

  get config(): WorkspaceConfig | null {
    return this._config;
  }

  async setup(mode: WorkspaceMode): Promise<WorkspaceConfig> {
    const username = os.userInfo().username;
    const windowsWorkspace = path.join(
      "C:",
      "Users",
      username,
      "DeerFlow",
      "workspace"
    );

    if (mode === "wsl_native") {
      return this.setupWSLNative(windowsWorkspace);
    } else {
      return this.setupWindowsMount(windowsWorkspace);
    }
  }

  private async setupWSLNative(
    windowsWorkspace: string
  ): Promise<WorkspaceConfig> {
    const wslPath = "/home/sandbox/workspace";

    await this.sandbox.execute("mkdir -p /home/sandbox/workspace", {
      timeout: 10,
    });

    await this.sandbox.execute(
      "chown sandbox:sandbox /home/sandbox/workspace",
      { timeout: 10 }
    );

    const windowsAccessPath =
      this.pathConverter.wslNativeToWindows(wslPath);

    this._config = {
      mode: "wsl_native",
      windowsPath: windowsAccessPath,
      wslPath,
      description:
        "工作目录位于 WSL2 原生文件系统，性能最佳。通过 \\\\wsl$\\DeerFlow 路径从 Windows 访问。",
    };

    return this._config;
  }

  private async setupWindowsMount(
    windowsWorkspace: string
  ): Promise<WorkspaceConfig> {
    let effectiveWindowsPath = windowsWorkspace;

    try {
      const hasChinese = /[\u4e00-\u9fff]/.test(windowsWorkspace);
      if (hasChinese) {
        const shortPath = await getShortPath(windowsWorkspace);
        if (shortPath !== windowsWorkspace) {
          effectiveWindowsPath = shortPath;
        }
      }
    } catch {}

    if (!fs.existsSync(effectiveWindowsPath)) {
      fs.mkdirSync(effectiveWindowsPath, { recursive: true });
    }

    const wslPath = this.pathConverter.windowsToWsl(effectiveWindowsPath);

    await this.sandbox.execute(
      `mkdir -p /home/sandbox && ln -sf ${wslPath} /home/sandbox/workspace`,
      { timeout: 10 }
    );

    this._config = {
      mode: "windows_mount",
      windowsPath: effectiveWindowsPath,
      wslPath,
      description:
        "工作目录位于 Windows 文件系统，Windows 原生可访问，但跨文件系统 IO 性能较差。",
    };

    return this._config;
  }

  async verifyAccess(): Promise<{
    windowsToWsl: boolean;
    wslToWindows: boolean;
    readWrite: boolean;
    issues: string[];
  }> {
    const issues: string[] = [];

    if (!this._config) {
      return {
        windowsToWsl: false,
        wslToWindows: false,
        readWrite: false,
        issues: ["工作目录未配置"],
      };
    }

    const testFileName = `.deerflow-test-${Date.now()}`;
    let windowsToWsl = false;
    let wslToWindows = false;
    let readWrite = false;

    try {
      if (this._config.mode === "windows_mount") {
        const testFilePath = path.join(this._config.windowsPath, testFileName);
        fs.writeFileSync(testFilePath, "test", "utf-8");

        const readResult = await this.sandbox.execute(
          `cat ${this._config.wslPath}/${testFileName}`,
          { timeout: 10 }
        );
        windowsToWsl = readResult.exitCode === 0 && readResult.stdout.trim() === "test";

        const writeResult = await this.sandbox.execute(
          `echo "wsl_test" > ${this._config.wslPath}/.wsl-${testFileName}`,
          { timeout: 10 }
        );

        if (writeResult.exitCode === 0) {
          const wslTestPath = path.join(
            this._config.windowsPath,
            `.wsl-${testFileName}`
          );
          try {
            const content = fs.readFileSync(wslTestPath, "utf-8");
            wslToWindows = content.trim() === "wsl_test";
            fs.unlinkSync(wslTestPath);
          } catch {}
        }

        try {
          fs.unlinkSync(testFilePath);
        } catch {}

        readWrite = windowsToWsl && wslToWindows;
      } else {
        const writeResult = await this.sandbox.execute(
          `echo "test" > ${this._config.wslPath}/${testFileName}`,
          { timeout: 10 }
        );

        if (writeResult.exitCode === 0) {
          const readResult = await this.sandbox.execute(
            `cat ${this._config.wslPath}/${testFileName}`,
            { timeout: 10 }
          );
          windowsToWsl = readResult.exitCode === 0 && readResult.stdout.trim() === "test";

          const windowsPath = this._config.windowsPath.replace(/\\/g, "/");
          const accessPath = `\\\\wsl$\\DeerFlow\\home\\sandbox\\workspace\\${testFileName}`;
          try {
            const content = fs.readFileSync(accessPath, "utf-8");
            wslToWindows = content.trim() === "test";
          } catch {
            issues.push("无法从 Windows 访问 WSL2 原生文件系统，请确认 \\\\wsl$ 路径可用");
          }

          await this.sandbox.execute(
            `rm -f ${this._config.wslPath}/${testFileName}`,
            { timeout: 10 }
          );
        }

        readWrite = windowsToWsl && wslToWindows;
      }
    } catch (err) {
      issues.push(
        `工作目录访问验证失败: ${err instanceof Error ? err.message : "未知错误"}`
      );
    }

    if (!windowsToWsl) issues.push("Windows → WSL2 文件访问失败");
    if (!wslToWindows) issues.push("WSL2 → Windows 文件访问失败");

    return { windowsToWsl, wslToWindows, readWrite, issues };
  }

  getPathConverter(): PathConverter {
    return this.pathConverter;
  }
}
