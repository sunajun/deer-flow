import React, { useState, useRef, useEffect, useCallback } from "react";
import LogEntry, { LogEntryData } from "./LogEntry";

interface OutputTabProps {
  logs: LogEntryData[];
  fontSize: number;
  autoScroll: boolean;
}

export default function OutputTab({ logs, fontSize, autoScroll }: OutputTabProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState("");

  const filteredLogs = searchTerm
    ? logs.filter(
        (log) =>
          log.message.toLowerCase().includes(searchTerm.toLowerCase()) ||
          (log.data && JSON.stringify(log.data).toLowerCase().includes(searchTerm.toLowerCase()))
      )
    : logs;

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filteredLogs.length, autoScroll]);

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "4px 8px",
          borderBottom: "1px solid var(--color-border)",
          gap: 8,
        }}
      >
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="搜索日志..."
          style={{
            flex: 1,
            background: "var(--color-bg)",
            border: "1px solid var(--color-border)",
            color: "var(--color-text)",
            padding: "4px 8px",
            borderRadius: 4,
            fontSize: 12,
            outline: "none",
          }}
        />
        {searchTerm && (
          <span style={{ color: "var(--color-text-secondary)", fontSize: 12 }}>
            {filteredLogs.length}/{logs.length}
          </span>
        )}
      </div>
      <div
        ref={containerRef}
        style={{
          flex: 1,
          overflowY: "auto",
          overflowX: "hidden",
        }}
      >
        {filteredLogs.map((log) => (
          <LogEntry
            key={log.id}
            entry={log}
            fontSize={fontSize}
            expanded={expandedIds.has(log.id)}
            onToggle={() => toggleExpand(log.id)}
          />
        ))}
        {filteredLogs.length === 0 && (
          <div
            style={{
              padding: 16,
              textAlign: "center",
              color: "var(--color-text-secondary)",
              fontSize: 12,
            }}
          >
            {searchTerm ? "无匹配日志" : "暂无 Agent 执行日志"}
          </div>
        )}
      </div>
    </div>
  );
}
