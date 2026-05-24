import { spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { app } from "electron";

export interface SandboxDetectionResult {
  type: "macos-vm" | "wsl2" | "firecracker" | "docker" | "local";
  available: boolean;
  details: Record<string, any>;
}

interface CachedDetection {
  result: SandboxDetectionResult;
  timestamp: number;
}

const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const CACHE_KEY = "deerflow:sandbox-detection-cache";

let cachedDetection: CachedDetection | null = null;

function loadCache(): void {
  try {
    const raw = localStorage?.getItem(CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as CachedDetection;
      if (Date.now() - parsed.timestamp < CACHE_TTL_MS) {
        cachedDetection = parsed;
      } else {
        localStorage?.removeItem(CACHE_KEY);
      }
    }
  } catch {
    // Ignore cache read errors
  }
}

function saveCache(result: SandboxDetectionResult): void {
  cachedDetection = { result, timestamp: Date.now() };
  try {
    localStorage?.setItem(CACHE_KEY, JSON.stringify(cachedDetection));
  } catch {
    // Ignore cache write errors
  }
}

function isCacheValid(): boolean {
  if (!cachedDetection) return false;
  return Date.now() - cachedDetection.timestamp < CACHE_TTL_MS;
}

async function execCommand(
  command: string,
  args: string[] = [],
  timeoutMs: number = 10000
): Promise<{ exitCode: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    try {
      const child = spawn(command, args, { timeout: timeoutMs });
      let stdout = "";
      let stderr = "";

      child.stdout?.on("data", (data: Buffer) => {
        stdout += data.toString();
      });
      child.stderr?.on("data", (data: Buffer) => {
        stderr += data.toString();
      });
      child.on("close", (code) => {
        resolve({ exitCode: code ?? -1, stdout, stderr });
      });
      child.on("error", (err) => {
        resolve({ exitCode: -1, stdout: "", stderr: err.message });
      });
    } catch (err: any) {
      resolve({ exitCode: -1, stdout: "", stderr: err.message || String(err) });
    }
  });
}

async function checkMacOSVirtualization(): Promise<Record<string, any> | null> {
  try {
    let cliPath: string;
    if (app.isPackaged) {
      cliPath = path.join(process.resourcesPath, "native", "DeerFlowSandboxCLI");
    } else {
      cliPath = path.resolve(
        __dirname,
        "../native/macos/.build/release/DeerFlowSandboxCLI"
      );
    }

    if (!fs.existsSync(cliPath)) {
      return null;
    }

    const result = await execCommand(cliPath, ["detect-support"], 15000);
    if (result.exitCode !== 0) {
      return null;
    }

    const data = JSON.parse(result.stdout.trim());
    if (data?.success && data?.data?.isSupported) {
      return data.data;
    }
    return null;
  } catch (err) {
    return null;
  }
}

async function checkWSL2Support(): Promise<Record<string, any>> {
  const result: Record<string, any> = {
    available: false,
    canInstall: false,
    wslInstalled: false,
    wsl2Default: false,
    deerFlowDistroInstalled: false,
  };

  try {
    const statusResult = await execCommand("wsl", ["--status"], 10000);
    if (statusResult.exitCode !== 0) {
      return result;
    }

    result.wslInstalled = true;

    const output = statusResult.stdout + statusResult.stderr;
    result.wsl2Default =
      output.includes("2") || output.toLowerCase().includes("default version: 2");

    const listResult = await execCommand("wsl", ["-l", "-q"], 10000);
    if (listResult.exitCode === 0) {
      result.deerFlowDistroInstalled = listResult.stdout.includes("DeerFlow");
    }

    result.available = result.wslInstalled && result.wsl2Default;
    result.canInstall = !result.wslInstalled || !result.wsl2Default;
  } catch {
    // WSL not available
  }

  return result;
}

async function offerWSL2Install(): Promise<boolean> {
  return false;
}

async function checkKVMSupport(): Promise<Record<string, any> | null> {
  try {
    if (!fs.existsSync("/dev/kvm")) {
      return null;
    }

    try {
      fs.accessSync("/dev/kvm", fs.constants.R_OK | fs.constants.W_OK);
    } catch {
      return { available: false, reason: "KVM 设备无读写权限" };
    }

    const whichResult = await execCommand("which", ["firecracker"], 5000);
    if (whichResult.exitCode !== 0) {
      return { available: false, reason: "Firecracker 二进制未找到" };
    }

    return { available: true, kvmDevice: "/dev/kvm" };
  } catch {
    return null;
  }
}

async function checkDockerSupport(): Promise<Record<string, any> | null> {
  try {
    const result = await execCommand("docker", ["info"], 10000);
    if (result.exitCode !== 0) {
      return null;
    }
    return { available: true };
  } catch {
    return null;
  }
}

export async function detectAndSetupSandbox(): Promise<SandboxDetectionResult> {
  loadCache();
  if (cachedDetection && isCacheValid()) {
    return cachedDetection.result;
  }

  const platform = process.platform;

  try {
    if (platform === "darwin") {
      const hasVirtualization = await checkMacOSVirtualization();
      if (hasVirtualization) {
        const result: SandboxDetectionResult = {
          type: "macos-vm",
          available: true,
          details: hasVirtualization,
        };
        saveCache(result);
        return result;
      }
    } else if (platform === "win32") {
      const hasWSL2 = await checkWSL2Support();
      if (hasWSL2.available) {
        const result: SandboxDetectionResult = {
          type: "wsl2",
          available: true,
          details: hasWSL2,
        };
        saveCache(result);
        return result;
      }
      if (hasWSL2.canInstall) {
        const installed = await offerWSL2Install();
        if (installed) {
          const result: SandboxDetectionResult = {
            type: "wsl2",
            available: true,
            details: { ...hasWSL2, installed: true },
          };
          saveCache(result);
          return result;
        }
      }
    } else if (platform === "linux") {
      const hasKVM = await checkKVMSupport();
      if (hasKVM?.available) {
        const result: SandboxDetectionResult = {
          type: "firecracker",
          available: true,
          details: hasKVM,
        };
        saveCache(result);
        return result;
      }
      const hasDocker = await checkDockerSupport();
      if (hasDocker?.available) {
        const result: SandboxDetectionResult = {
          type: "docker",
          available: true,
          details: hasDocker,
        };
        saveCache(result);
        return result;
      }
    }
  } catch (error) {
    console.error("沙箱检测失败:", error);
  }

  const result: SandboxDetectionResult = {
    type: "local",
    available: true,
    details: { reason: "未检测到虚拟化能力，将使用本地模式" },
  };
  saveCache(result);
  return result;
}

export function invalidateDetectionCache(): void {
  cachedDetection = null;
  try {
    localStorage?.removeItem(CACHE_KEY);
  } catch {
    // Ignore
  }
}
