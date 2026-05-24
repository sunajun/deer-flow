import React from "react";

interface ConsoleToolbarProps {
  fontSize: number;
  onFontSizeChange: (size: number) => void;
  autoScroll: boolean;
  onAutoScrollChange: (enabled: boolean) => void;
  onClear: () => void;
  onExport: () => void;
  logCount: number;
}

export default function ConsoleToolbar({
  fontSize,
  onFontSizeChange,
  autoScroll,
  onAutoScrollChange,
  onClear,
  onExport,
  logCount,
}: ConsoleToolbarProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 12px",
        background: "var(--color-surface)",
        borderBottom: "1px solid var(--color-border)",
        fontSize: 12,
      }}
    >
      <span style={{ color: "var(--color-text-secondary)" }}>
        {logCount} 条日志
      </span>

      <div style={{ flex: 1 }} />

      <button
        onClick={() => onFontSizeChange(Math.max(10, fontSize - 1))}
        style={toolbarBtnStyle}
        title="缩小字体"
      >
        A-
      </button>
      <span style={{ color: "var(--color-text-secondary)", minWidth: 28, textAlign: "center" }}>
        {fontSize}
      </span>
      <button
        onClick={() => onFontSizeChange(Math.min(18, fontSize + 1))}
        style={toolbarBtnStyle}
        title="放大字体"
      >
        A+
      </button>

      <div style={{ width: 1, height: 16, background: "var(--color-border)" }} />

      <button
        onClick={() => onAutoScrollChange(!autoScroll)}
        style={{
          ...toolbarBtnStyle,
          color: autoScroll ? "var(--color-primary)" : "var(--color-text-secondary)",
        }}
        title={autoScroll ? "关闭自动滚动" : "开启自动滚动"}
      >
        {autoScroll ? "⤓ 自动" : "⤓ 手动"}
      </button>

      <button onClick={onExport} style={toolbarBtnStyle} title="导出日志">
        导出
      </button>

      <button onClick={onClear} style={{ ...toolbarBtnStyle, color: "var(--color-error)" }} title="清空日志">
        清空
      </button>
    </div>
  );
}

const toolbarBtnStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid var(--color-border)",
  color: "var(--color-text-secondary)",
  padding: "2px 8px",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 12,
  fontFamily: "inherit",
};
