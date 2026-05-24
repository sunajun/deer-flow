import { app, BrowserWindow } from "electron";
import * as fs from "fs";
import * as path from "path";
import { EventEmitter } from "events";

export interface LogEntry {
  id: string;
  timestamp: number;
  level: "debug" | "info" | "warn" | "error";
  source: "backend" | "electron" | "sandbox" | "network";
  message: string;
  data?: unknown;
}

type LogLevel = LogEntry["level"];
type LogSource = LogEntry["source"];

const FLUSH_INTERVAL = 100;
const MAX_BUFFER_SIZE = 1000;
const MAX_LOG_FILE_SIZE = 10 * 1024 * 1024;
const MAX_LOG_DAYS = 7;

export class Logger extends EventEmitter {
  private buffer: LogEntry[] = [];
  private flushTimer: NodeJS.Timeout | null = null;
  private logDir: string;
  private currentLogFile: string;
  private consoleOpen = false;
  private idCounter = 0;

  constructor() {
    super();
    this.logDir = path.join(app.getPath("home"), "DeerFlow", "logs");
    this.currentLogFile = this.getLogFilePath(new Date());
    this.ensureLogDir();
    this.cleanOldLogs();
    this.startFlushTimer();
  }

  private ensureLogDir(): void {
    if (!fs.existsSync(this.logDir)) {
      fs.mkdirSync(this.logDir, { recursive: true });
    }
  }

  private getLogFilePath(date: Date): string {
    const dateStr = date.toISOString().split("T")[0];
    return path.join(this.logDir, `deerflow-${dateStr}.log`);
  }

  private generateId(): string {
    return `${Date.now()}-${++this.idCounter}`;
  }

  private startFlushTimer(): void {
    this.flushTimer = setInterval(() => {
      this.flush();
    }, FLUSH_INTERVAL);
  }

  private cleanOldLogs(): void {
    try {
      const files = fs.readdirSync(this.logDir);
      const now = Date.now();
      const maxAge = MAX_LOG_DAYS * 24 * 60 * 60 * 1000;

      for (const file of files) {
        if (!file.startsWith("deerflow-") || !file.endsWith(".log")) continue;
        const filePath = path.join(this.logDir, file);
        const stat = fs.statSync(filePath);
        if (now - stat.mtimeMs > maxAge) {
          fs.unlinkSync(filePath);
        }
      }
    } catch {
      // ignore cleanup errors
    }
  }

  private checkLogRotation(): void {
    try {
      if (!fs.existsSync(this.currentLogFile)) return;
      const stat = fs.statSync(this.currentLogFile);
      if (stat.size >= MAX_LOG_FILE_SIZE) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
        const rotatedPath = path.join(this.logDir, `deerflow-${timestamp}.log`);
        fs.renameSync(this.currentLogFile, rotatedPath);
        this.currentLogFile = this.getLogFilePath(new Date());
      }
    } catch {
      // ignore rotation errors
    }
  }

  log(level: LogLevel, source: LogSource, message: string, data?: unknown): void {
    const entry: LogEntry = {
      id: this.generateId(),
      timestamp: Date.now(),
      level,
      source,
      message,
      ...(data !== undefined ? { data } : {}),
    };

    this.buffer.push(entry);

    if (this.buffer.length > MAX_BUFFER_SIZE) {
      this.buffer = this.buffer.slice(-MAX_BUFFER_SIZE);
    }

    const consoleLevel = level === "error" ? "error" : level === "warn" ? "warn" : "log";
    const prefix = `[${source}]`;
    if (data !== undefined) {
      console[consoleLevel](prefix, message, data);
    } else {
      console[consoleLevel](prefix, message);
    }
  }

  debug(source: LogSource, message: string, data?: unknown): void {
    this.log("debug", source, message, data);
  }

  info(source: LogSource, message: string, data?: unknown): void {
    this.log("info", source, message, data);
  }

  warn(source: LogSource, message: string, data?: unknown): void {
    this.log("warn", source, message, data);
  }

  error(source: LogSource, message: string, data?: unknown): void {
    this.log("error", source, message, data);
  }

  setConsoleOpen(open: boolean): void {
    this.consoleOpen = open;
  }

  flush(): void {
    if (this.buffer.length === 0) return;

    const entries = this.buffer.splice(0);
    this.writeToFile(entries);

    if (this.consoleOpen) {
      this.sendToRenderer(entries);
    }
  }

  private writeToFile(entries: LogEntry[]): void {
    try {
      this.checkLogRotation();
      const lines = entries.map((e) => JSON.stringify(e)).join("\n") + "\n";
      fs.appendFileSync(this.currentLogFile, lines, "utf-8");
    } catch (err) {
      console.error("[Logger] Failed to write log file:", err);
    }
  }

  private sendToRenderer(entries: LogEntry[]): void {
    const windows = BrowserWindow.getAllWindows();
    for (const win of windows) {
      if (!win.isDestroyed()) {
        win.webContents.send("console:log", entries);
      }
    }
  }

  getRecentLogs(count: number = 100): LogEntry[] {
    try {
      if (!fs.existsSync(this.currentLogFile)) return [];
      const content = fs.readFileSync(this.currentLogFile, "utf-8");
      const lines = content.trim().split("\n").filter(Boolean);
      const recent = lines.slice(-count);
      return recent.map((line) => {
        try {
          return JSON.parse(line) as LogEntry;
        } catch {
          return null;
        }
      }).filter((e): e is LogEntry => e !== null);
    } catch {
      return [];
    }
  }

  exportLogs(outputPath: string): boolean {
    try {
      this.flush();
      const files = fs.readdirSync(this.logDir)
        .filter((f) => f.startsWith("deerflow-") && f.endsWith(".log"))
        .sort();

      const allLines: string[] = [];
      for (const file of files) {
        const content = fs.readFileSync(path.join(this.logDir, file), "utf-8");
        allLines.push(content);
      }

      fs.writeFileSync(outputPath, allLines.join("\n"), "utf-8");
      return true;
    } catch {
      return false;
    }
  }

  clearLogs(): boolean {
    try {
      this.flush();
      const files = fs.readdirSync(this.logDir)
        .filter((f) => f.startsWith("deerflow-") && f.endsWith(".log"));

      for (const file of files) {
        fs.unlinkSync(path.join(this.logDir, file));
      }

      this.currentLogFile = this.getLogFilePath(new Date());
      return true;
    } catch {
      return false;
    }
  }

  destroy(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer);
      this.flushTimer = null;
    }
    this.flush();
    this.removeAllListeners();
  }
}
