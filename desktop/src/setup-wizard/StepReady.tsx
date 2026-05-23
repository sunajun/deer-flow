import React from "react";
import type { WizardConfig } from "./SetupWizard";

interface StepReadyProps {
  config: WizardConfig;
  onComplete: () => void;
  onBack: () => void;
}

export default function StepReady({ config, onComplete, onBack }: StepReadyProps) {
  const apiKeysConfigured = Object.values(config.apiKeys).some((v) => v.trim().length > 0);
  const providerNames = Object.entries(config.apiKeys)
    .filter(([, v]) => v.trim().length > 0)
    .map(([k]) => k.charAt(0).toUpperCase() + k.slice(1));

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 8 }}>You're All Set!</h2>
      <p style={{ color: "var(--color-text-secondary)", fontSize: 14, marginBottom: 24 }}>
        Review your configuration and launch DeerFlow.
      </p>

      <div style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
        overflow: "hidden",
        marginBottom: 32,
      }}>
        <SummaryRow
          label="Sandbox Mode"
          value={config.sandboxMode}
          detail={config.sandboxAvailable ? `Using ${config.sandboxType}` : "No virtualization available"}
        />
        <SummaryRow
          label="API Keys"
          value={apiKeysConfigured ? `${providerNames.length} configured` : "Not configured"}
          detail={apiKeysConfigured ? providerNames.join(", ") : "Can be added later in Settings"}
        />
        <SummaryRow
          label="Skills"
          value={`${config.selectedSkills.length} selected`}
          detail={config.selectedSkills.join(", ")}
          last
        />
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
          onClick={onComplete}
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
          Launch DeerFlow
        </button>
      </div>
    </div>
  );
}

function SummaryRow({
  label,
  value,
  detail,
  last = false,
}: {
  label: string;
  value: string;
  detail: string;
  last?: boolean;
}) {
  return (
    <div style={{
      padding: "14px 16px",
      borderBottom: last ? "none" : "1px solid var(--color-border)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>{label}</span>
        <span style={{ fontSize: 13, fontWeight: 500 }}>{value}</span>
      </div>
      <div style={{ fontSize: 12, color: "var(--color-text-secondary)" }}>{detail}</div>
    </div>
  );
}
