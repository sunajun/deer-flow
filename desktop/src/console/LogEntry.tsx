import React from "react";

export interface LogEntryData {
  id: string;
  timestamp: number;
  level: "debug" | "info" | "warn" | "error";
  source: "backend" | "electron" | "sandbox" | "network";
  message: string;
  data?: unknown;
}

interface LogEntryProps {
  entry: LogEntryData;
  fontSize: number;
  expanded?: boolean;
  onToggle?: () => void;
}

const levelColors: Record<string, string> = {
  debug: "var(--color-text-secondary)",
  info: "var(--color-text)",
  warn: "var(--color-warning)",
  error: "var(--color-error)",
};

const sourceLabels: Record<string, string> = {
  backend: "BE",
  electron: "EL",
  sandbox: "SB",
  network: "NW",
};

const sourceColors: Record<string, string> = {
  backend: "var(--color-primary)",
  electron: "var(--color-success)",
  sandbox: "var(--color-warning)",
  network: "#8b5cf6",
};

export default function LogEntry({ entry, fontSize, expanded, onToggle }: LogEntryProps) {
  const time = new Date(entry.timestamp).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const hasData = entry.data !== undefined;
  const dataStr = hasData ? JSON.stringify(entry.data, null, 2) : "";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        padding: "2px 8px",
        fontSize,
        fontFamily: "monospace",
        lineHeight: 1.5,
        borderBottom: "1px solid var(--color-border)",
        cursor: hasData ? "pointer" : "default",
      }}
      onClick={hasData ? onToggle : undefined}
    >
      <span style={{ color: "var(--color-text-secondary)", flexShrink: 0, fontSize: "0.85em" }}>
        {time}
      </span>
      <span
        style={{
          color: sourceColors[entry.source] || "var(--color-text-secondary)",
          flexShrink: 0,
          fontWeight: 600,
          fontSize: "0.85em",
        }}
      >
        {sourceLabels[entry.source] || entry.source}
      </span>
      <span
        style={{
          color: levelColors[entry.level],
          flexShrink: 0,
          fontWeight: entry.level === "error" || entry.level === "warn" ? 600 : 400,
          fontSize: "0.85em",
          width: 16,
          textAlign: "center",
        }}
      >
        {entry.level === "error" ? "✕" : entry.level === "warn" ? "⚠" : entry.level === "info" ? "●" : "·"}
      </span>
      <span style={{ color: levelColors[entry.level], wordBreak: "break-word", flex: 1 }}>
        {entry.message}
        {hasData && (
          <span style={{ color: "var(--color-text-secondary)", marginLeft: 4, fontSize: "0.85em" }}>
            {expanded ? "▼" : "▶"}
          </span>
        )}
      </span>
      {expanded && hasData && (
        <pre
          style={{
            margin: 0,
            padding: "4px 0",
            color: "var(--color-text-secondary)",
            fontSize: "0.9em",
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}
        >
          {dataStr}
        </pre>
      )}
    </div>
  );
}
