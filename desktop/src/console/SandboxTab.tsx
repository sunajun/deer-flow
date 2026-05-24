import React, { useState } from "react";
import { LogEntryData } from "./LogEntry";

interface SandboxCommand {
  id: string;
  timestamp: number;
  command: string;
  exitCode: number | null;
  stdout: string;
  stderr: string;
}

interface SandboxTabProps {
  logs: LogEntryData[];
  sandboxState: string;
  sandboxType: string;
  fontSize: number;
}

export default function SandboxTab({ logs, sandboxState, sandboxType, fontSize }: SandboxTabProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const sandboxLogs = logs.filter((l) => l.source === "sandbox");

  const commands: SandboxCommand[] = sandboxLogs
    .filter((l) => l.data && typeof l.data === "object")
    .map((l) => {
      const d = l.data as Record<string, unknown>;
      return {
        id: l.id,
        timestamp: l.timestamp,
        command: (d.command as string) || l.message,
        exitCode: (d.exitCode as number) ?? null,
        stdout: (d.stdout as string) || "",
        stderr: (d.stderr as string) || "",
      };
    });

  const stateColor = sandboxState === "running"
    ? "var(--color-success)"
    : sandboxState === "paused"
      ? "var(--color-warning)"
      : sandboxState === "error"
        ? "var(--color-error)"
        : "var(--color-text-secondary)";

  const typeLabel = sandboxType === "virtualization-framework"
    ? "macOS VM"
    : sandboxType === "wsl2"
      ? "WSL2"
      : sandboxType === "firecracker"
        ? "Firecracker"
        : "本地模式";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "8px 12px",
          borderBottom: "1px solid var(--color-border)",
          fontSize,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: stateColor,
              display: "inline-block",
            }}
          />
          <span>{sandboxState === "running" ? "运行中" : sandboxState === "paused" ? "已暂停" : sandboxState === "error" ? "错误" : "未启动"}</span>
        </div>
        <span style={{ color: "var(--color-text-secondary)" }}>|</span>
        <span style={{ color: "var(--color-text-secondary)" }}>{typeLabel}</span>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {commands.length === 0 ? (
          <div
            style={{
              padding: 16,
              textAlign: "center",
              color: "var(--color-text-secondary)",
              fontSize: 12,
            }}
          >
            暂无沙箱命令日志
          </div>
        ) : (
          commands.map((cmd) => (
            <div
              key={cmd.id}
              style={{
                borderBottom: "1px solid var(--color-border)",
                cursor: "pointer",
              }}
              onClick={() => setExpandedId(expandedId === cmd.id ? null : cmd.id)}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "4px 12px",
                  fontSize,
                  fontFamily: "monospace",
                }}
              >
                <span style={{ color: "var(--color-text-secondary)", fontSize: "0.85em" }}>
                  {new Date(cmd.timestamp).toLocaleTimeString("en-US", { hour12: false })}
                </span>
                <span style={{ flex: 1, color: "var(--color-text)" }}>$ {cmd.command}</span>
                {cmd.exitCode !== null && (
                  <span
                    style={{
                      color: cmd.exitCode === 0 ? "var(--color-success)" : "var(--color-error)",
                      fontSize: "0.85em",
                    }}
                  >
                    exit {cmd.exitCode}
                  </span>
                )}
                <span style={{ color: "var(--color-text-secondary)", fontSize: "0.85em" }}>
                  {expandedId === cmd.id ? "▼" : "▶"}
                </span>
              </div>
              {expandedId === cmd.id && (
                <div style={{ padding: "4px 12px 8px", fontSize: fontSize - 1, fontFamily: "monospace" }}>
                  {cmd.stdout && (
                    <pre style={{ margin: 0, color: "var(--color-text)", whiteSpace: "pre-wrap" }}>
                      {cmd.stdout}
                    </pre>
                  )}
                  {cmd.stderr && (
                    <pre style={{ margin: 0, color: "var(--color-error)", whiteSpace: "pre-wrap" }}>
                      {cmd.stderr}
                    </pre>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
