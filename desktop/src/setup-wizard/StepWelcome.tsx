import React from "react";

interface StepWelcomeProps {
  onNext: () => void;
}

export default function StepWelcome({ onNext }: StepWelcomeProps) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{
        width: 72,
        height: 72,
        margin: "0 auto 24px",
        borderRadius: 16,
        background: "linear-gradient(135deg, var(--color-primary), #a855f7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 36,
      }}>
        🦌
      </div>

      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>
        Welcome to DeerFlow
      </h1>

      <p style={{
        color: "var(--color-text-secondary)",
        fontSize: 15,
        lineHeight: 1.6,
        marginBottom: 32,
      }}>
        Your AI-powered agent workspace. Let's set up a few things to get you started.
      </p>

      <div style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
        padding: 16,
        marginBottom: 32,
        textAlign: "left",
      }}>
        <p style={{ fontSize: 13, color: "var(--color-text-secondary)", marginBottom: 8 }}>
          System Requirements:
        </p>
        <ul style={{ fontSize: 13, color: "var(--color-text-secondary)", paddingLeft: 20, lineHeight: 1.8 }}>
          <li>Python 3.11+ (bundled in production)</li>
          <li>4 GB RAM minimum</li>
          <li>Internet connection for LLM API access</li>
        </ul>
      </div>

      <button
        onClick={onNext}
        style={{
          padding: "12px 48px",
          background: "var(--color-primary)",
          color: "#fff",
          border: "none",
          borderRadius: "var(--radius)",
          fontSize: 15,
          fontWeight: 600,
          transition: "background 0.2s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-primary-hover)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "var(--color-primary)")}
      >
        Start Setup
      </button>
    </div>
  );
}
