import { spawn, ChildProcess } from "child_process";
import * as path from "path";
import { app } from "electron";
import { EventEmitter } from "events";

export interface VirtualizationSupport {
  isSupported: boolean;
  chipArchitecture: "apple_silicon" | "intel";
  macOSVersion: string;
  minimumRequirement: string;
  reason: string | null;
  supportedFeatures: string[];
}

export interface VMConfig {
  imagePath: string;
  kernelPath?: string;
  memoryMB: number;
  cpuCount: number;
  workspacePath: string;
  sshPort?: number;
  architecture: "apple_silicon" | "intel";
}

export interface CommandResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  error?: string;
}

export interface SnapshotInfo {
  name: string;
  createdAt: string;
  sizeBytes: number;
  description: string | null;
  architecture: string;
  isNative: boolean;
}

type SandboxState = "stopped" | "starting" | "running" | "paused" | "error";

export class VMSandboxManager extends EventEmitter {
  private cliPath: string;
  private sandboxId: string | null = null;
  private _state: SandboxState = "stopped";

  constructor(cliPath?: string) {
    super();
    this.cliPath = cliPath || this.resolveCLIPath();
  }

  get state(): SandboxState {
    return this._state;
  }

  private setState(state: SandboxState): void {
    this._state = state;
    this.emit("state-change", state);
  }

  async detectSupport(): Promise<VirtualizationSupport> {
    const result = await this.callCLI("detect-support");
    if (!result.success || !result.data) {
      return {
        isSupported: false,
        chipArchitecture: "apple_silicon",
        macOSVersion: "unknown",
        minimumRequirement: "macOS 11.0 (Big Sur)",
        reason: result.error || "Failed to detect support",
        supportedFeatures: [],
      };
    }
    return result.data as VirtualizationSupport;
  }

  async createSandbox(config: VMConfig): Promise<string> {
    const args = JSON.stringify(config);
    const result = await this.callCLI("create-sandbox", { args });
    if (!result.success || !result.id) {
      throw new Error(result.error || "Failed to create sandbox");
    }
    this.sandboxId = result.id as string;
    return this.sandboxId;
  }

  async startSandbox(id?: string): Promise<boolean> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) throw new Error("No sandbox ID");

    this.setState("starting");
    const result = await this.callCLI("start-sandbox", { id: sandboxId });

    if (result.success) {
      this.setState("running");
    } else {
      this.setState("error");
    }

    return result.success;
  }

  async stopSandbox(id?: string): Promise<boolean> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) return false;

    const result = await this.callCLI("stop-sandbox", { id: sandboxId });

    if (result.success) {
      this.sandboxId = null;
      this.setState("stopped");
    }

    return result.success;
  }

  async execute(
    command: string,
    timeout: number = 300,
    id?: string
  ): Promise<CommandResult> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) throw new Error("No sandbox ID");

    const result = await this.callCLI("execute", {
      id: sandboxId,
      command,
      timeout,
    });

    if (result.data) {
      return result.data as CommandResult;
    }

    return {
      exitCode: -1,
      stdout: "",
      stderr: result.error || "Unknown error",
    };
  }

  async pauseSandbox(id?: string): Promise<boolean> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) return false;

    const result = await this.callCLI("pause-sandbox", { id: sandboxId });
    if (result.success) {
      this.setState("paused");
    }
    return result.success;
  }

  async resumeSandbox(id?: string): Promise<boolean> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) return false;

    const result = await this.callCLI("resume-sandbox", { id: sandboxId });
    if (result.success) {
      this.setState("running");
    }
    return result.success;
  }

  async saveSnapshot(name: string, id?: string): Promise<boolean> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) return false;

    const result = await this.callCLI("save-snapshot", {
      id: sandboxId,
      name,
    });
    return result.success;
  }

  async restoreSnapshot(name: string, id?: string): Promise<boolean> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) return false;

    const result = await this.callCLI("restore-snapshot", {
      id: sandboxId,
      name,
    });
    return result.success;
  }

  async listSnapshots(id?: string): Promise<SnapshotInfo[]> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) return [];

    const result = await this.callCLI("list-snapshots", { id: sandboxId });
    if (result.data && Array.isArray(result.data)) {
      return result.data as SnapshotInfo[];
    }
    return [];
  }

  async deleteSnapshot(name: string, id?: string): Promise<boolean> {
    const sandboxId = id || this.sandboxId;
    if (!sandboxId) return false;

    const result = await this.callCLI("delete-snapshot", {
      id: sandboxId,
      name,
    });
    return result.success;
  }

  async getDefaultConfig(): Promise<Partial<VMConfig>> {
    const result = await this.callCLI("default-config");
    if (result.data) {
      return result.data as Partial<VMConfig>;
    }
    return {};
  }

  private resolveCLIPath(): string {
    if (app.isPackaged) {
      return path.join(
        process.resourcesPath,
        "native",
        "DeerFlowSandboxCLI"
      );
    }

    return path.resolve(
      __dirname,
      "../native/macos/.build/release/DeerFlowSandboxCLI"
    );
  }

  private callCLI(
    action: string,
    params?: Record<string, string | number>
  ): Promise<Record<string, any>> {
    return new Promise((resolve, reject) => {
      const args: string[] = [action];

      if (params) {
        for (const [key, value] of Object.entries(params)) {
          args.push(`--${key}`, String(value));
        }
      }

      const child = spawn(this.cliPath, args, {
        stdio: ["pipe", "pipe", "pipe"],
      });

      let stdout = "";
      let stderr = "";

      child.stdout.on("data", (data: Buffer) => {
        stdout += data.toString();
      });

      child.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
      });

      child.on("close", (code) => {
        if (stdout.trim()) {
          try {
            const result = JSON.parse(stdout.trim());
            resolve(result);
          } catch {
            resolve({
              success: false,
              error: `Failed to parse CLI output: ${stdout}`,
            });
          }
        } else {
          resolve({
            success: false,
            error: stderr.trim() || `CLI exited with code ${code}`,
          });
        }
      });

      child.on("error", (err) => {
        resolve({
          success: false,
          error: `Failed to launch CLI: ${err.message}`,
        });
      });

      const timeout = setTimeout(() => {
        child.kill();
        resolve({
          success: false,
          error: "CLI call timed out",
        });
      }, 60000);

      child.on("close", () => {
        clearTimeout(timeout);
      });
    });
  }
}
