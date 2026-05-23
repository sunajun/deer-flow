import React, { useState, useEffect } from "react";
import type { WizardConfig } from "./SetupWizard";

interface StepSandboxProps {
  config: WizardConfig;
  onUpdate: (partial: Partial<WizardConfig>) => void;
  onNext: () => void;
  onBack: () => void;
}

const SANDBOX_MODES = [
  {
    id: "STRICT" as const,
    label: "Strict",
    description: "All code execution in sandbox. Maximum security.",
  },
  {
    id: "SELECTIVE" as const,
    label: "Selective (Recommended)",
    description: "Sandbox only for risky operations. Balanced security and convenience.",
  },
  {
    id: "LOCAL" as const,
    label: "Local",
    description: "No sandbox. Direct execution on host. Use only for trusted environments.",
  },
];

export default function StepSandbox({ config, onUpdate, onNext, onBack }: StepSandboxProps) {
  const [detecting, setDetecting] = useState(false);
  const [detected, setDetected] = useState(false);

  useEffect(() => {
    if (!detected) {
      detectSandbox();
    }
  }, []);

  const detectSandbox = async () => {
    setDetecting(true);
    try {
      if (window.deerflow) {
        const result = await window.deerflow.detectSandbox();
        onUpdate({
          sandboxType: result.type,
          sandboxAvailable: result.available,
          sandboxMode: result.available ? "SELECTIVE" : "LOCAL",
        });
      }
    } catch {
      onUpdate({ sandboxAvailable: false, sandboxMode: "LOCAL" });
    } finally {
      setDetecting(false);
      setDetected(true);
    }
  };

  const platformLabel = () => {
    switch (config.sandboxType) {
      case "virtualization-framework": return "macOS Virtualization.framework";
      case "wsl2": return "Windows WSL2";
      case "kvm": return "Linux KVM";
      default: return "Unknown";
    }
  };

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 8 }}>Sandbox Configuration</h2>
      <p style={{ color: "var(--color-text-secondary)", fontSize: 14, marginBottom: 24 }}>
        Choose how DeerFlow executes code and tools on your system.
      </p>

      <div style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
        padding: 16,
        marginBottom: 24,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {detecting ? (
            <>
              <div style={{
                width: 20,
                height: 20,
                border: "2px solid var(--color-border)",
                borderTopColor: "var(--color-primary)",
                borderRadius: "50%",
                animation: "spin 1s linear infinite",
              }} />
              <span style={{ fontSize: 14, color: "var(--color-text-secondary)" }}>
                Detecting virtualization capabilities...
              </span>
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </>
          ) : (
            <>
              <div style={{
                width: 20,
                height: 20,
                borderRadius: "50%",
                background: config.sandboxAvailable ? "var(--color-success)" : "var(--color-warning)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
              }}>
                {config.sandboxAvailable ? "✓" : "!"}
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{platformLabel()}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>
                  {config.sandboxAvailable
                    ? "Virtualization available — sandbox mode supported"
                    : "No virtualization detected — local mode recommended"}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 32 }}>
        {SANDBOX_MODES.map((mode) => (
          <label
            key={mode.id}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 12,
              padding: 16,
              background: config.sandboxMode === mode.id ? "rgba(99, 102, 241, 0.1)" : "var(--color-surface)",
              border: `1px solid ${config.sandboxMode === mode.id ? "var(--color-primary)" : "var(--color-border)"}`,
              borderRadius: "var(--radius)",
              cursor: "pointer",
              transition: "all 0.2s",
            }}
          >
            <input
              type="radio"
              name="sandbox-mode"
              value={mode.id}
              checked={config.sandboxMode === mode.id}
              onChange={() => onUpdate({ sandboxMode: mode.id })}
              style={{ marginTop: 2 }}
            />
            <div>
              <div style={{ fontSize: 14, fontWeight: 500 }}>{mode.label}</div>
              <div style={{ fontSize: 12, color: "var(--color-text-secondary)", marginTop: 2 }}>
                {mode.description}
              </div>
            </div>
          </label>
        ))}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <button
          onClick={onBack}
          style={{
            padding: "10px 24px",
            background: "transparent",
            color: "var(--color-text-secondary)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            fontSize: 14,
          }}
        >
          Back
        </button>
        <button
          onClick={onNext}
          style={{
            padding: "10px 32px",
            background: "var(--color-primary)",
            color: "#fff",
            border: "none",
            borderRadius: "var(--radius)",
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          Next
        </button>
      </div>
    </div>
  );
}
