import React, { useState } from "react";
import type { WizardConfig } from "./SetupWizard";

interface StepApiKeyProps {
  config: WizardConfig;
  onUpdate: (partial: Partial<WizardConfig>) => void;
  onNext: () => void;
  onBack: () => void;
}

const PROVIDERS = [
  { id: "openai", label: "OpenAI", envVar: "OPENAI_API_KEY", placeholder: "sk-..." },
  { id: "anthropic", label: "Anthropic", envVar: "ANTHROPIC_API_KEY", placeholder: "sk-ant-..." },
  { id: "custom", label: "Custom Provider", envVar: "", placeholder: "Enter API key" },
];

export default function StepApiKey({ config, onUpdate, onNext, onBack }: StepApiKeyProps) {
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  const setApiKey = (providerId: string, value: string) => {
    onUpdate({ apiKeys: { ...config.apiKeys, [providerId]: value } });
  };

  const toggleShowKey = (providerId: string) => {
    setShowKeys((prev) => ({ ...prev, [providerId]: !prev[providerId] }));
  };

  const hasAnyKey = Object.values(config.apiKeys).some((v) => v.trim().length > 0);

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 8 }}>API Key Configuration</h2>
      <p style={{ color: "var(--color-text-secondary)", fontSize: 14, marginBottom: 24 }}>
        Configure your LLM provider API keys. You can skip this and add them later.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 24 }}>
        {PROVIDERS.map((provider) => (
          <div
            key={provider.id}
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              padding: 16,
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 8 }}>{provider.label}</div>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type={showKeys[provider.id] ? "text" : "password"}
                value={config.apiKeys[provider.id] || ""}
                onChange={(e) => setApiKey(provider.id, e.target.value)}
                placeholder={provider.placeholder}
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  background: "var(--color-bg)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                  color: "var(--color-text)",
                  fontSize: 14,
                  outline: "none",
                }}
              />
              <button
                onClick={() => toggleShowKey(provider.id)}
                style={{
                  padding: "8px 12px",
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                  color: "var(--color-text-secondary)",
                  fontSize: 12,
                }}
              >
                {showKeys[provider.id] ? "Hide" : "Show"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {!hasAnyKey && (
        <div style={{
          padding: 12,
          background: "rgba(245, 158, 11, 0.1)",
          border: "1px solid rgba(245, 158, 11, 0.3)",
          borderRadius: "var(--radius)",
          marginBottom: 24,
          fontSize: 13,
          color: "var(--color-warning)",
        }}>
          No API keys configured. You can add them later in Settings.
        </div>
      )}

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
          {hasAnyKey ? "Next" : "Skip for now"}
        </button>
      </div>
    </div>
  );
}
