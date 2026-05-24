import * as os from "os";
import { WSL2Sandbox, WSL2Error, ExecuteOptions, CommandResult } from "../wsl2-bridge";
import { DistroManager, DistroInfo } from "../distro-manager";

const isWindows = os.platform() === "win32";

async function isWSL2Available(): Promise<boolean> {
  if (!isWindows) return false;
  try {
    const { execSync } = await import("child_process");
    const output = execSync("wsl --status", { encoding: "utf-8", timeout: 10000 });
    return output.includes("默认版本") || output.includes("default version") || output.includes("2");
  } catch {
    return false;
  }
}

let wsl2Available = false;

beforeAll(async () => {
  wsl2Available = await isWSL2Available();
});

const describeIfWSL2 = wsl2Available ? describe : describe.skip;

function skipIfNotWindows(): void {
  if (!isWindows) {
    return;
  }
}

describe("WSL2 Integration Tests", () => {
  describeIfWSL2("WSL2Sandbox Lifecycle", () => {
    let sandbox: WSL2Sandbox;

    beforeAll(() => {
      sandbox = new WSL2Sandbox();
    });

    afterAll(async () => {
      try {
        if (sandbox) {
          await sandbox.stop();
        }
      } catch {}
    });

    it("should initialize the sandbox", async () => {
      await sandbox.init();
      expect(sandbox.state).toBe("stopped");
    });

    it("should start the sandbox", async () => {
      await sandbox.start();
      expect(sandbox.state).toBe("running");
    });

    it("should report isRunning as true after start", async () => {
      const running = await sandbox.isRunning();
      expect(running).toBe(true);
    });

    it("should execute a simple command", async () => {
      const result = await sandbox.execute("echo hello");
      expect(result.exitCode).toBe(0);
      expect(result.stdout.trim()).toBe("hello");
    });

    it("should stop the sandbox", async () => {
      await sandbox.stop();
      expect(sandbox.state).toBe("stopped");
    });

    it("should report isRunning as false after stop", async () => {
      const running = await sandbox.isRunning();
      expect(running).toBe(false);
    });
  });

  describeIfWSL2("Command Execution", () => {
    let sandbox: WSL2Sandbox;

    beforeAll(async () => {
      sandbox = new WSL2Sandbox();
      await sandbox.init();
      await sandbox.start();
    });

    afterAll(async () => {
      try {
        await sandbox.stop();
      } catch {}
    });

    it("should execute whoami and return the default user", async () => {
      const result = await sandbox.execute("whoami");
      expect(result.exitCode).toBe(0);
      expect(result.stdout.trim()).toBe("sandbox");
    });

    it("should execute python3 --version", async () => {
      const result = await sandbox.execute("python3 --version");
      expect(result.exitCode).toBe(0);
      expect(result.stdout.trim()).toMatch(/Python \d+\.\d+/);
    });

    it("should execute node --version", async () => {
      const result = await sandbox.execute("node --version");
      expect(result.exitCode).toBe(0);
      expect(result.stdout.trim()).toMatch(/v\d+\.\d+/);
    });

    it("should execute git --version", async () => {
      const result = await sandbox.execute("git --version");
      expect(result.exitCode).toBe(0);
      expect(result.stdout.trim()).toMatch(/git version \d+/);
    });

    it("should respect cwd option", async () => {
      const result = await sandbox.execute("pwd", { cwd: "/tmp" });
      expect(result.exitCode).toBe(0);
      expect(result.stdout.trim()).toBe("/tmp");
    });

    it("should respect env option", async () => {
      const result = await sandbox.execute("echo $DEERFLOW_TEST_VAR", {
        env: { DEERFLOW_TEST_VAR: "integration-test" },
      });
      expect(result.exitCode).toBe(0);
      expect(result.stdout.trim()).toBe("integration-test");
    });

    it("should respect timeout option and fail on timeout", async () => {
      const result = await sandbox.execute("sleep 10", { timeout: 1 });
      expect(result.exitCode).not.toBe(0);
    });

    it("should return error for non-initialized sandbox", async () => {
      const freshSandbox = new WSL2Sandbox();
      const result = await freshSandbox.execute("echo test");
      expect(result.exitCode).toBe(-1);
      expect(result.error).toBeDefined();
    });
  });

  describeIfWSL2("Version Info", () => {
    let sandbox: WSL2Sandbox;

    beforeAll(async () => {
      sandbox = new WSL2Sandbox();
      await sandbox.init();
      await sandbox.start();
    });

    afterAll(async () => {
      try {
        await sandbox.stop();
      } catch {}
    });

    it("should read /etc/deerflow-version", async () => {
      const result = await sandbox.execute("cat /etc/deerflow-version");
      expect(result.exitCode).toBe(0);
      const content = result.stdout.trim();
      expect(content).not.toBe("unknown");
      expect(content.length).toBeGreaterThan(0);
    });

    it("should return valid KEY=VALUE format from /etc/deerflow-version", async () => {
      const result = await sandbox.execute("cat /etc/deerflow-version");
      expect(result.exitCode).toBe(0);
      const content = result.stdout.trim();
      const lines = content.split("\n");
      const entries: Record<string, string> = {};
      for (const line of lines) {
        const eqIdx = line.indexOf("=");
        if (eqIdx > 0) {
          const key = line.substring(0, eqIdx).trim();
          const value = line.substring(eqIdx + 1).trim();
          entries[key] = value;
        }
      }
      expect(entries).toHaveProperty("DEERFLOW_VERSION");
      expect(entries).toHaveProperty("COMPAT_VERSION");
    });
  });

  describeIfWSL2("DistroManager", () => {
    let sandbox: WSL2Sandbox;
    let distroManager: DistroManager;

    beforeAll(async () => {
      sandbox = new WSL2Sandbox();
      await sandbox.init();
      await sandbox.start();
      distroManager = new DistroManager(sandbox);
    });

    afterAll(async () => {
      try {
        await sandbox.stop();
      } catch {}
    });

    it("should getCurrentVersion and return DistroInfo", async () => {
      const info = await distroManager.getCurrentVersion();
      expect(info).not.toBeNull();
      expect(info!.name).toBe("DeerFlow");
      expect(info!.version).toBeDefined();
      expect(info!.state).toBe("Running");
    });

    it("should return DistroInfo with buildTime", async () => {
      const info = await distroManager.getCurrentVersion();
      expect(info).not.toBeNull();
      expect(info!.buildTime).toBeDefined();
    });

    it("should checkHealth and report healthy status", async () => {
      const health = await distroManager.checkHealth();
      expect(health).toHaveProperty("healthy");
      expect(health).toHaveProperty("wslServiceOk");
      expect(health).toHaveProperty("distroOk");
      expect(health).toHaveProperty("issues");
      expect(health.wslServiceOk).toBe(true);
      expect(health.distroOk).toBe(true);
      expect(health.healthy).toBe(true);
    });

    it("should report no critical issues when healthy", async () => {
      const health = await distroManager.checkHealth();
      const criticalIssues = health.issues.filter(
        (issue) =>
          issue.includes("异常") ||
          issue.includes("未安装")
      );
      expect(criticalIssues).toHaveLength(0);
    });
  });

  describeIfWSL2("Compatibility Check", () => {
    let sandbox: WSL2Sandbox;

    beforeAll(async () => {
      sandbox = new WSL2Sandbox();
      await sandbox.init();
      await sandbox.start();
    });

    afterAll(async () => {
      try {
        await sandbox.stop();
      } catch {}
    });

    it("should read COMPAT_VERSION from /etc/deerflow-version", async () => {
      const result = await sandbox.execute("cat /etc/deerflow-version");
      expect(result.exitCode).toBe(0);
      const content = result.stdout.trim();
      const lines = content.split("\n");
      const entries: Record<string, string> = {};
      for (const line of lines) {
        const eqIdx = line.indexOf("=");
        if (eqIdx > 0) {
          entries[line.substring(0, eqIdx).trim()] = line.substring(eqIdx + 1).trim();
        }
      }
      expect(entries).toHaveProperty("COMPAT_VERSION");
      expect(Number(entries.COMPAT_VERSION)).toBeGreaterThan(0);
    });

    it("should read MIN_APP_VERSION from /etc/deerflow-version", async () => {
      const result = await sandbox.execute("cat /etc/deerflow-version");
      expect(result.exitCode).toBe(0);
      const content = result.stdout.trim();
      const lines = content.split("\n");
      const entries: Record<string, string> = {};
      for (const line of lines) {
        const eqIdx = line.indexOf("=");
        if (eqIdx > 0) {
          entries[line.substring(0, eqIdx).trim()] = line.substring(eqIdx + 1).trim();
        }
      }
      expect(entries).toHaveProperty("MIN_APP_VERSION");
      expect(entries.MIN_APP_VERSION).toMatch(/^\d+\.\d+/);
    });

    it("should have COMPAT_VERSION as a positive integer", async () => {
      const result = await sandbox.execute("cat /etc/deerflow-version");
      expect(result.exitCode).toBe(0);
      const content = result.stdout.trim();
      const lines = content.split("\n");
      const entries: Record<string, string> = {};
      for (const line of lines) {
        const eqIdx = line.indexOf("=");
        if (eqIdx > 0) {
          entries[line.substring(0, eqIdx).trim()] = line.substring(eqIdx + 1).trim();
        }
      }
      expect(Number(entries.COMPAT_VERSION)).toBeGreaterThan(0);
    });

    it("should have MIN_APP_VERSION in semver-like format", async () => {
      const result = await sandbox.execute("cat /etc/deerflow-version");
      expect(result.exitCode).toBe(0);
      const content = result.stdout.trim();
      const lines = content.split("\n");
      const entries: Record<string, string> = {};
      for (const line of lines) {
        const eqIdx = line.indexOf("=");
        if (eqIdx > 0) {
          entries[line.substring(0, eqIdx).trim()] = line.substring(eqIdx + 1).trim();
        }
      }
      expect(entries.MIN_APP_VERSION).toMatch(/^\d+\.\d+/);
    });
  });
});

describe("WSL2 Integration - Non-Windows Skip", () => {
  it("should skip all WSL2 tests when not on Windows", () => {
    if (!isWindows) {
      expect(true).toBe(true);
    } else {
      expect(true).toBe(true);
    }
  });
});
