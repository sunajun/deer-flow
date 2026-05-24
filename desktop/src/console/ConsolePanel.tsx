import React, { useState, useEffect, useRef, useCallback } from "react";
import OutputTab from "./OutputTab";
import SandboxTab from "./SandboxTab";
import NetworkTab from "./NetworkTab";
import SystemTab from "./SystemTab";
import ConsoleToolbar from "./ConsoleToolbar";
import { LogEntryData } from "./LogEntry";

type TabType = "output" | "sandbox" | "network" | "system";

interface ConsolePanelProps {
  visible: boolean;
  onToggle: () => void;
  sandboxState: string;
  sandboxType: string;
}

const DEFAULT_HEIGHT = 200;
const MIN_HEIGHT = 100;
const MAX_HEIGHT = 600;
const DEFAULT_FONT_SIZE = 13;

const tabs: { key: TabType; label: string }[] = [
  { key: "output", label: "输出" },
  { key: "sandbox", label: "沙箱" },
  { key: "network", label: "网络" },
  { key: "system", label: "系统" },
];

export default function ConsolePanel({ visible, onToggle, sandboxState, sandboxType }: ConsolePanelProps) {
  const [activeTab, setActiveTab] = useState<TabType>("output");
  const [logs, setLogs] = useState<LogEntryData[]>([]);
  const [fontSize, setFontSize] = useState(DEFAULT_FONT_SIZE);
  const [autoScroll, setAutoScroll] = useState(true);
  const [height, setHeight] = useState(DEFAULT_HEIGHT);
  const [isDragging, setIsDragging] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const dragStartY = useRef(0);
  const dragStartHeight = useRef(0);

  useEffect(() => {
    if (!window.deerflow?.onConsoleLog) return;

    const unsub = window.deerflow.onConsoleLog((entries: LogEntryData[]) => {
      setLogs((prev) => [...prev, ...entries].slice(-5000));
    });

    return unsub;
  }, []);

  useEffect(() => {
    if (window.deerflow?.setConsoleOpen) {
      window.deerflow.setConsoleOpen(visible);
    }
  }, [visible]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === "C") {
        e.preventDefault();
        onToggle();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onToggle]);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartY.current = e.clientY;
    dragStartHeight.current = height;
  }, [height]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = dragStartY.current - e.clientY;
      const newHeight = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, dragStartHeight.current + delta));
      setHeight(newHeight);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging]);

  const handleClear = useCallback(() => {
    setLogs([]);
    if (window.deerflow?.clearLogs) {
      window.deerflow.clearLogs();
    }
  }, []);

  const handleExport = useCallback(() => {
    if (window.deerflow?.exportLogs) {
      window.deerflow.exportLogs();
    }
  }, []);

  if (!visible) return null;

  return (
    <div
      ref={panelRef}
      style={{
        display: "flex",
        flexDirection: "column",
        height,
        borderTop: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        flexShrink: 0,
      }}
    >
      <div
        onMouseDown={handleDragStart}
        style={{
          height: 4,
          cursor: "ns-resize",
          background: isDragging ? "var(--color-primary)" : "var(--color-border)",
          flexShrink: 0,
          transition: "background 0.15s",
        }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          borderBottom: "1px solid var(--color-border)",
          flexShrink: 0,
        }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              background: "none",
              border: "none",
              borderBottom: activeTab === tab.key ? "2px solid var(--color-primary)" : "2px solid transparent",
              color: activeTab === tab.key ? "var(--color-text)" : "var(--color-text-secondary)",
              padding: "6px 16px",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: activeTab === tab.key ? 600 : 400,
            }}
          >
            {tab.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button
          onClick={onToggle}
          style={{
            background: "none",
            border: "none",
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            padding: "4px 8px",
            fontSize: 14,
          }}
          title="关闭控制台 (Ctrl+Shift+C)"
        >
          ✕
        </button>
      </div>

      <ConsoleToolbar
        fontSize={fontSize}
        onFontSizeChange={setFontSize}
        autoScroll={autoScroll}
        onAutoScrollChange={setAutoScroll}
        onClear={handleClear}
        onExport={handleExport}
        logCount={logs.length}
      />

      <div style={{ flex: 1, overflow: "hidden" }}>
        {activeTab === "output" && (
          <OutputTab logs={logs} fontSize={fontSize} autoScroll={autoScroll} />
        )}
        {activeTab === "sandbox" && (
          <SandboxTab
            logs={logs}
            sandboxState={sandboxState}
            sandboxType={sandboxType}
            fontSize={fontSize}
          />
        )}
        {activeTab === "network" && (
          <NetworkTab logs={logs} fontSize={fontSize} />
        )}
        {activeTab === "system" && (
          <SystemTab logs={logs} fontSize={fontSize} autoScroll={autoScroll} />
        )}
      </div>
    </div>
  );
}
