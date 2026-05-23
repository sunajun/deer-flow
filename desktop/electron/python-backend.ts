import { ChildProcess, spawn } from "child_process";
import { EventEmitter } from "events";
import * as net from "net";
import * as path from "path";
import * as http from "http";
import { app } from "electron";

type BackendStatus = "starting" | "ready" | "error" | "stopped";

const DEFAULT_PORT = 8001;
const MAX_PORT = 8010;
const HEALTH_CHECK_INTERVAL = 1000;
const HEALTH_CHECK_MAX_RETRIES = 30;
const SHUTDOWN_TIMEOUT = 5000;
const MAX_RESTART_ATTEMPTS = 3;
const RESTART_DELAY = 10000;

export class PythonBackendManager extends EventEmitter {
  private process: ChildProcess | null = null;
  private _port: number = DEFAULT_PORT;
  private _status: BackendStatus = "stopped";
  private restartAttempts = 0;
  private restartTimer: NodeJS.Timeout | null = null;
  private healthCheckTimer: NodeJS.Timeout | null = null;

  get port(): number {
    return this._port;
  }

  get status(): BackendStatus {
    return this._status;
  }

  private setStatus(status: BackendStatus): void {
    this._status = status;
    this.emit("status", status);
  }

  private isDevMode(): boolean {
    return !app.isPackaged;
  }

  private getBackendCommand(): { command: string; args: string[] } {
    if (this.isDevMode()) {
      const backendDir = path.resolve(__dirname, "../../../backend");
      return {
        command: "uv",
        args: ["run", "uvicorn", "app.gateway.app:app", "--host", "127.0.0.1", "--port", String(this._port)],
      };
    }

    const resourcesPath = process.resourcesPath;
    const ext = process.platform === "win32" ? ".exe" : "";
    const binaryPath = path.join(resourcesPath, "python-backend", `deerflow-backend${ext}`);

    return {
      command: binaryPath,
      args: ["--host", "127.0.0.1", "--port", String(this._port)],
    };
  }

  private async findAvailablePort(startPort: number): Promise<number> {
    for (let port = startPort; port <= MAX_PORT; port++) {
      const available = await this.isPortAvailable(port);
      if (available) return port;
    }
    throw new Error(`No available port in range ${startPort}-${MAX_PORT}`);
  }

  private isPortAvailable(port: number): Promise<boolean> {
    return new Promise((resolve) => {
      const server = net.createServer();
      server.once("error", () => resolve(false));
      server.once("listening", () => {
        server.close();
        resolve(true);
      });
      server.listen(port, "127.0.0.1");
    });
  }

  async start(): Promise<void> {
    if (this._status === "starting" || this._status === "ready") {
      return;
    }

    this.setStatus("starting");

    try {
      this._port = await this.findAvailablePort(DEFAULT_PORT);
    } catch (err) {
      this.setStatus("error");
      this.emit("status", `Port conflict: ${err}`);
      return;
    }

    this.emit("port", this._port);

    const { command, args } = this.getBackendCommand();

    const env: Record<string, string | undefined> = {
      ...process.env,
      GATEWAY_HOST: "127.0.0.1",
      GATEWAY_PORT: String(this._port),
    };

    if (this.isDevMode()) {
      const configPath = path.resolve(__dirname, "../../../config.yaml");
      env.DEER_FLOW_CONFIG_PATH = configPath;
    }

    this.process = spawn(command, args, {
      cwd: this.isDevMode() ? path.resolve(__dirname, "../../../backend") : undefined,
      env,
      stdio: ["pipe", "pipe", "pipe"],
    });

    this.process.stdout?.on("data", (data: Buffer) => {
      const output = data.toString();
      console.log(`[Python Backend] ${output.trim()}`);
    });

    this.process.stderr?.on("data", (data: Buffer) => {
      const output = data.toString();
      console.error(`[Python Backend] ${output.trim()}`);
    });

    this.process.on("exit", (code, signal) => {
      console.log(`[Python Backend] Process exited with code ${code}, signal ${signal}`);
      if (this._status !== "stopped" && this._status !== "error") {
        this.handleUnexpectedExit(code, signal);
      }
    });

    this.process.on("error", (err) => {
      console.error(`[Python Backend] Process error:`, err);
      this.setStatus("error");
    });

    await this.waitForHealthCheck();
  }

  private waitForHealthCheck(): Promise<void> {
    return new Promise((resolve, reject) => {
      let attempts = 0;

      const check = () => {
        attempts++;

        if (attempts > HEALTH_CHECK_MAX_RETRIES) {
          this.setStatus("error");
          reject(new Error("Health check timeout"));
          return;
        }

        const url = `http://127.0.0.1:${this._port}/health`;
        const req = http.get(url, (res) => {
          if (res.statusCode === 200) {
            this.setStatus("ready");
            this.restartAttempts = 0;
            resolve();
          } else {
            this.healthCheckTimer = setTimeout(check, HEALTH_CHECK_INTERVAL);
          }
        });

        req.on("error", () => {
          this.healthCheckTimer = setTimeout(check, HEALTH_CHECK_INTERVAL);
        });

        req.setTimeout(2000, () => {
          req.destroy();
          this.healthCheckTimer = setTimeout(check, HEALTH_CHECK_INTERVAL);
        });
      };

      this.healthCheckTimer = setTimeout(check, HEALTH_CHECK_INTERVAL);
    });
  }

  private handleUnexpectedExit(code: number | null, signal: string | null): void {
    if (this.restartAttempts >= MAX_RESTART_ATTEMPTS) {
      this.setStatus("error");
      console.error(
        `[Python Backend] Max restart attempts (${MAX_RESTART_ATTEMPTS}) reached. Last exit: code=${code}, signal=${signal}`
      );
      return;
    }

    this.restartAttempts++;
    console.log(
      `[Python Backend] Attempting restart ${this.restartAttempts}/${MAX_RESTART_ATTEMPTS} in ${RESTART_DELAY / 1000}s...`
    );

    this.restartTimer = setTimeout(async () => {
      try {
        this.process = null;
        await this.start();
      } catch (err) {
        console.error(`[Python Backend] Restart attempt ${this.restartAttempts} failed:`, err);
      }
    }, RESTART_DELAY);
  }

  async stop(): Promise<void> {
    if (this.healthCheckTimer) {
      clearTimeout(this.healthCheckTimer);
      this.healthCheckTimer = null;
    }

    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }

    if (!this.process || this.process.exitCode !== null) {
      this.setStatus("stopped");
      return;
    }

    return new Promise((resolve) => {
      const pid = this.process!.pid;
      const timeout = setTimeout(() => {
        if (pid) {
          if (process.platform === "win32") {
            spawn("taskkill", ["/PID", String(pid), "/F"]);
          } else {
            process.kill(pid, "SIGKILL");
          }
        }
        this.setStatus("stopped");
        resolve();
      }, SHUTDOWN_TIMEOUT);

      this.process!.on("exit", () => {
        clearTimeout(timeout);
        this.setStatus("stopped");
        resolve();
      });

      try {
        if (process.platform === "win32") {
          spawn("taskkill", ["/PID", String(pid), "/F"]);
        } else {
          this.process!.kill("SIGTERM");
        }
      } catch {
        clearTimeout(timeout);
        this.setStatus("stopped");
        resolve();
      }
    });
  }

  async restart(): Promise<void> {
    await this.stop();
    this.restartAttempts = 0;
    await this.start();
  }
}
