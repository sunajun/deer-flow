import * as path from "path";
import * as os from "os";
import * as fs from "fs";
import { runCommand } from "./windows-version";
import { WSL2Sandbox } from "./wsl2-bridge";

export interface DistroInfo {
  name: string;
  version: string;
  buildTime: string;
  state: "Running" | "Stopped" | "none";
}

export interface DistroUpdateResult {
  success: boolean;
  message: string;
  error?: string;
}

export class DistroManager {
  private sandbox: WSL2Sandbox;
  private distroName = "DeerFlow";

  constructor(sandbox: WSL2Sandbox) {
    this.sandbox = sandbox;
  }

  async importDistro(imagePath: string): Promise<void> {
    if (!fs.existsSync(imagePath)) {
      throw new Error(`发行版镜像文件不存在: ${imagePath}`);
    }

    const localAppData =
      process.env.LOCALAPPDATA ||
      path.join(os.homedir(), "AppData", "Local");
    const installPath = path.join(localAppData, "DeerFlow", "wsl-distro");

    if (!fs.existsSync(installPath)) {
      fs.mkdirSync(installPath, { recursive: true });
    }

    const result = await runCommand(
      `wsl --import ${this.distroName} "${installPath}" "${imagePath}" --version 2`,
      300000
    );

    if (result.exitCode !== 0) {
      throw new Error(`发行版导入失败: ${result.stderr}`);
    }

    await this.configureDistro();
  }

  async getCurrentVersion(): Promise<DistroInfo | null> {
    const result = await this.sandbox.execute("cat /etc/deerflow-version 2>/dev/null || echo unknown", {
      timeout: 10,
    });

    if (result.exitCode !== 0 || result.stdout.trim() === "unknown") {
      return null;
    }

    try {
      const data = JSON.parse(result.stdout.trim());
      return {
        name: this.distroName,
        version: data.version || "unknown",
        buildTime: data.buildTime || "unknown",
        state: (await this.sandbox.isRunning()) ? "Running" : "Stopped",
      };
    } catch {
      return {
        name: this.distroName,
        version: result.stdout.trim(),
        buildTime: "unknown",
        state: (await this.sandbox.isRunning()) ? "Running" : "Stopped",
      };
    }
  }

  async update(newImagePath: string): Promise<DistroUpdateResult> {
    const localAppData =
      process.env.LOCALAPPDATA ||
      path.join(os.homedir(), "AppData", "Local");
    const backupDir = path.join(localAppData, "DeerFlow", "backup");

    if (!fs.existsSync(backupDir)) {
      fs.mkdirSync(backupDir, { recursive: true });
    }

    try {
      const userDataBackup = await this.exportUserData(backupDir);

      const isRunning = await this.sandbox.isRunning();
      if (isRunning) {
        await this.sandbox.stop();
      }

      await this.unregisterDistro();

      await this.importDistro(newImagePath);

      if (userDataBackup) {
        await this.importUserData(userDataBackup);
        try {
          fs.unlinkSync(userDataBackup);
        } catch {}
      }

      await this.sandbox.start();

      return {
        success: true,
        message: "发行版更新成功，用户数据已恢复",
      };
    } catch (err) {
      return {
        success: false,
        message: "发行版更新失败",
        error: err instanceof Error ? err.message : "未知错误",
      };
    }
  }

  async exportUserData(backupDir: string): Promise<string | null> {
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const backupPath = path.join(backupDir, `user-data-${timestamp}.tar`);

    const result = await runCommand(
      `wsl -d ${this.distroName} -- bash -c "tar cf - /home/sandbox/ 2>/dev/null" > "${backupPath}"`,
      60000
    );

    if (result.exitCode !== 0) {
      return null;
    }

    return fs.existsSync(backupPath) ? backupPath : null;
  }

  async importUserData(backupPath: string): Promise<boolean> {
    if (!fs.existsSync(backupPath)) return false;

    const windowsBackupPath = backupPath.replace(/\\/g, "/");
    const wslBackupPath = `/mnt/c${windowsBackupPath.substring(2)}`;

    const result = await this.sandbox.execute(
      `tar xf ${wslBackupPath} -C / 2>/dev/null`,
      { timeout: 60 }
    );

    return result.exitCode === 0;
  }

  async checkHealth(): Promise<{
    healthy: boolean;
    wslServiceOk: boolean;
    distroOk: boolean;
    issues: string[];
  }> {
    const issues: string[] = [];
    let wslServiceOk = true;
    let distroOk = true;

    const statusResult = await runCommand("wsl --status", 10000);
    if (statusResult.exitCode !== 0) {
      wslServiceOk = false;
      issues.push("WSL 服务异常");
    }

    const isRunning = await this.sandbox.isRunning();
    if (!isRunning) {
      const listResult = await runCommand("wsl -l -v", 10000);
      if (listResult.stdout.includes(this.distroName)) {
        distroOk = true;
        issues.push("发行版已停止");
      } else {
        distroOk = false;
        issues.push("DeerFlow 发行版未安装");
      }
    }

    if (isRunning) {
      const testResult = await this.sandbox.execute("echo health_check", {
        timeout: 10,
      });
      if (testResult.exitCode !== 0) {
        distroOk = false;
        issues.push("发行版命令执行异常");
      }
    }

    return {
      healthy: wslServiceOk && distroOk,
      wslServiceOk,
      distroOk,
      issues,
    };
  }

  async repairWslService(): Promise<boolean> {
    const result = await runCommand("wsl --shutdown", 30000);
    if (result.exitCode !== 0) {
      return false;
    }

    await new Promise((resolve) => setTimeout(resolve, 2000));
    return true;
  }

  private async unregisterDistro(): Promise<void> {
    const result = await runCommand(
      `wsl --unregister ${this.distroName}`,
      30000
    );
    if (result.exitCode !== 0) {
      throw new Error(`注销旧发行版失败: ${result.stderr}`);
    }
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

    const localAppData =
      process.env.LOCALAPPDATA ||
      path.join(os.homedir(), "AppData", "Local");
    const confDir = path.join(localAppData, "DeerFlow", "wsl-distro");
    const confPath = path.join(confDir, "wsl.conf");
    fs.writeFileSync(confPath, wslConf, "utf-8");

    const windowsConfPath = confPath.replace(/\\/g, "/");
    const wslConfPath = `/mnt/c${windowsConfPath.substring(2)}`;

    await this.sandbox.execute(
      `cp ${wslConfPath} /etc/wsl.conf`,
      { timeout: 10 }
    );

    await this.sandbox.execute(
      "useradd -m -s /bin/bash sandbox 2>/dev/null || true",
      { timeout: 10 }
    );
    await this.sandbox.execute(
      "usermod -aG sudo sandbox 2>/dev/null || true",
      { timeout: 10 }
    );

    try {
      fs.unlinkSync(confPath);
    } catch {}
  }
}
