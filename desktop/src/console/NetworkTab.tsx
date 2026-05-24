import React, { useState } from "react";
import { LogEntryData } from "./LogEntry";

interface NetworkRequest {
  id: string;
  timestamp: number;
  method: string;
  url: string;
  statusCode: number | null;
  duration: number | null;
  requestBody?: unknown;
  responseBody?: unknown;
}

interface NetworkTabProps {
  logs: LogEntryData[];
  fontSize: number;
}

export default function NetworkTab({ logs, fontSize }: NetworkTabProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const networkLogs = logs.filter((l) => l.source === "network");

  const requests: NetworkRequest[] = networkLogs.map((l) => {
    const d = (l.data as Record<string, unknown>) || {};
    return {
      id: l.id,
      timestamp: l.timestamp,
      method: (d.method as string) || "GET",
      url: (d.url as string) || l.message,
      statusCode: (d.statusCode as number) ?? null,
      duration: (d.duration as number) ?? null,
      requestBody: d.requestBody,
      responseBody: d.responseBody,
    };
  });

  const statusColor = (code: number | null): string => {
    if (!code) return "var(--color-text-secondary)";
    if (code >= 200 && code < 300) return "var(--color-success)";
    if (code >= 400 && code < 500) return "var(--color-warning)";
    if (code >= 500) return "var(--color-error)";
    return "var(--color-text-secondary)";
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {requests.length === 0 ? (
          <div
            style={{
              padding: 16,
              textAlign: "center",
              color: "var(--color-text-secondary)",
              fontSize: 12,
            }}
          >
            暂无网络请求日志
          </div>
        ) : (
          requests.map((req) => (
            <div
              key={req.id}
              style={{
                borderBottom: "1px solid var(--color-border)",
                cursor: "pointer",
              }}
              onClick={() => setExpandedId(expandedId === req.id ? null : req.id)}
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
                  {new Date(req.timestamp).toLocaleTimeString("en-US", { hour12: false })}
                </span>
                <span
                  style={{
                    color: "var(--color-primary)",
                    fontWeight: 600,
                    fontSize: "0.85em",
                    minWidth: 36,
                  }}
                >
                  {req.method}
                </span>
                <span style={{ flex: 1, color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {req.url}
                </span>
                {req.statusCode !== null && (
                  <span style={{ color: statusColor(req.statusCode), fontSize: "0.85em" }}>
                    {req.statusCode}
                  </span>
                )}
                {req.duration !== null && (
                  <span style={{ color: "var(--color-text-secondary)", fontSize: "0.85em" }}>
                    {req.duration}ms
                  </span>
                )}
                <span style={{ color: "var(--color-text-secondary)", fontSize: "0.85em" }}>
                  {expandedId === req.id ? "▼" : "▶"}
                </span>
              </div>
              {expandedId === req.id && (
                <div style={{ padding: "4px 12px 8px", fontSize: fontSize - 1, fontFamily: "monospace" }}>
                  {req.requestBody != null && (
                    <div style={{ marginBottom: 4 }}>
                      <div style={{ color: "var(--color-text-secondary)", fontSize: "0.85em", marginBottom: 2 }}>Request:</div>
                      <pre style={{ margin: 0, color: "var(--color-text)", whiteSpace: "pre-wrap", background: "var(--color-bg)", padding: 4, borderRadius: 4 }}>
                        {String(JSON.stringify(req.requestBody, null, 2))}
                      </pre>
                    </div>
                  )}
                  {req.responseBody != null && (
                    <div>
                      <div style={{ color: "var(--color-text-secondary)", fontSize: "0.85em", marginBottom: 2 }}>Response:</div>
                      <pre style={{ margin: 0, color: "var(--color-text)", whiteSpace: "pre-wrap", background: "var(--color-bg)", padding: 4, borderRadius: 4 }}>
                        {String(JSON.stringify(req.responseBody, null, 2))}
                      </pre>
                    </div>
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
