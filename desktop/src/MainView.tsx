import React from "react";

interface MainViewProps {
  backendStatus: string;
}

export default function MainView({ backendStatus }: MainViewProps) {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      height: "100%",
      gap: 16,
    }}>
      {backendStatus === "ready" ? (
        <>
          <h1 style={{ fontSize: 24, fontWeight: 600 }}>DeerFlow</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>Backend is running. Main workspace coming soon.</p>
        </>
      ) : backendStatus === "error" ? (
        <>
          <h1 style={{ fontSize: 24, fontWeight: 600, color: "var(--color-error)" }}>Backend Error</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>Failed to start the Python backend. Please check logs.</p>
          <button
            onClick={() => window.deerflow?.restartBackend()}
            style={{
              padding: "8px 24px",
              background: "var(--color-primary)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius)",
              fontSize: 14,
            }}
          >
            Restart Backend
          </button>
        </>
      ) : (
        <>
          <div style={{
            width: 32,
            height: 32,
            border: "3px solid var(--color-border)",
            borderTopColor: "var(--color-primary)",
            borderRadius: "50%",
            animation: "spin 1s linear infinite",
          }} />
          <p style={{ color: "var(--color-text-secondary)" }}>Starting Python backend...</p>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </>
      )}
    </div>
  );
}
