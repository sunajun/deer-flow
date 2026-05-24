import React from "react";

interface MainViewProps {
  backendStatus: string;
  sandboxState: string;
  sandboxType: string;
  consoleVisible: boolean;
  onToggleConsole: () => void;
  onOpenSettings: () => void;
}

export default function MainView({
  backendStatus,
  sandboxState,
  sandboxType,
  consoleVisible,
  onToggleConsole,
  onOpenSettings,
}: MainViewProps) {
  const sandboxStateColor = sandboxState === "running"
    ? "var(--color-success)"
    : sandboxState === "paused"
      ? "var(--color-warning)"
      : sandboxState === "error"
        ? "var(--color-error)"
        : "var(--color-text-secondary)";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          height: 36,
          padding: "0 12px",
          borderBottom: "1px solid var(--color-border)",
          background: "var(--color-surface)",
          flexShrink: 0,
          WebkitAppRegion: "drag",
        } as React.CSSProperties}
      >
        <span style={{ fontSize: 13, fontWeight: 600 }}>DeerFlow</span>

        <div style={{ flex: 1 }} />

        <div style={{ display: "flex", alignItems: "center", gap: 8, WebkitAppRegion: "no-drag" } as React.CSSProperties}>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: sandboxStateColor,
              display: "inline-block",
            }}
          />
          <span style={{ fontSize: 11, color: "var(--color-text-secondary)" }}>
            {sandboxState === "running" ? "沙箱运行中" : sandboxState === "paused" ? "沙箱已暂停" : "沙箱未启动"}
          </span>

          <div style={{ width: 1, height: 14, background: "var(--color-border)", margin: "0 4px" }} />

          <button
            onClick={onToggleConsole}
            style={headerBtnStyle}
            title="控制台 (Ctrl+Shift+C)"
          >
            ⌨
          </button>
          <button
            onClick={onOpenSettings}
            style={headerBtnStyle}
            title="偏好设置"
          >
            ⚙
          </button>
        </div>
      </div>

      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        {backendStatus === "ready" ? (
          <iframe
            src={window.location.origin + "/api/flow"}
            style={{
              width: "100%",
              height: "100%",
              border: "none",
              background: "var(--color-bg)",
            }}
            title="DeerFlow"
          />
        ) : backendStatus === "error" ? (
          <div style={centerStyle}>
            <h1 style={{ fontSize: 24, fontWeight: 600, color: "var(--color-error)" }}>Backend Error</h1>
            <p style={{ color: "var(--color-text-secondary)" }}>
              Failed to start the Python backend. Please check logs.
            </p>
            <button
              onClick={() => window.deerflow?.restartBackend()}
              style={primaryBtnStyle}
            >
              Restart Backend
            </button>
          </div>
        ) : (
          <div style={centerStyle}>
            <div style={{
              width: 32,
              height: 32,
              border: "3px solid var(--color-border)",
              borderTopColor: "var(--color-primary)",
              borderRadius: "50%",
              animation: "spin 1s linear infinite",
            }} />
            <p style={{ color: "var(--color-text-secondary)", marginTop: 12 }}>
              Starting Python backend...
            </p>
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}
      </div>
    </div>
  );
}

const centerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  height: "100%",
  gap: 16,
};

const headerBtnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--color-text-secondary)",
  cursor: "pointer",
  fontSize: 14,
  padding: "4px 6px",
  borderRadius: 4,
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "8px 24px",
  background: "var(--color-primary)",
  color: "#fff",
  border: "none",
  borderRadius: "var(--radius)",
  fontSize: 14,
  cursor: "pointer",
};
