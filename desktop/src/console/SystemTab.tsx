import React from "react";
import LogEntry, { LogEntryData } from "./LogEntry";

interface SystemTabProps {
  logs: LogEntryData[];
  fontSize: number;
  autoScroll: boolean;
}

export default function SystemTab({ logs, fontSize, autoScroll }: SystemTabProps) {
  const containerRef = React.useRef<HTMLDivElement>(null);

  const systemLogs = logs.filter(
    (l) => l.source === "backend" || l.source === "electron"
  );

  React.useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [systemLogs.length, autoScroll]);

  const errorLogs = systemLogs.filter((l) => l.level === "error");

  const copyErrors = () => {
    const text = errorLogs
      .map((l) => `[${new Date(l.timestamp).toISOString()}] [${l.level}] [${l.source}] ${l.message}${l.data ? "\n" + JSON.stringify(l.data, null, 2) : ""}`)
      .join("\n\n");
    navigator.clipboard.writeText(text);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {errorLogs.length > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "4px 12px",
            borderBottom: "1px solid var(--color-border)",
            background: "rgba(239, 68, 68, 0.1)",
          }}
        >
          <span style={{ color: "var(--color-error)", fontSize: 12 }}>
            {errorLogs.length} 个错误
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={copyErrors}
            style={{
              background: "none",
              border: "1px solid var(--color-error)",
              color: "var(--color-error)",
              padding: "2px 8px",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 11,
            }}
          >
            复制错误信息
          </button>
        </div>
      )}
      <div
        ref={containerRef}
        style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}
      >
        {systemLogs.map((log) => (
          <LogEntry key={log.id} entry={log} fontSize={fontSize} />
        ))}
        {systemLogs.length === 0 && (
          <div
            style={{
              padding: 16,
              textAlign: "center",
              color: "var(--color-text-secondary)",
              fontSize: 12,
            }}
          >
            暂无系统日志
          </div>
        )}
      </div>
    </div>
  );
}
