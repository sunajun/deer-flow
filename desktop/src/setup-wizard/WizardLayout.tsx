import React from "react";

interface WizardLayoutProps {
  currentStep: number;
  steps: { id: string; title: string }[];
  children: React.ReactNode;
}

export default function WizardLayout({ currentStep, steps, children }: WizardLayoutProps) {
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100%",
      background: "var(--color-bg)",
    }}>
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        padding: "24px 32px",
        borderBottom: "1px solid var(--color-border)",
      }}>
        {steps.map((step, index) => (
          <React.Fragment key={step.id}>
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              opacity: index <= currentStep ? 1 : 0.4,
            }}>
              <div style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 600,
                background: index < currentStep
                  ? "var(--color-success)"
                  : index === currentStep
                    ? "var(--color-primary)"
                    : "var(--color-surface)",
                color: index <= currentStep ? "#fff" : "var(--color-text-secondary)",
                border: index > currentStep ? "1px solid var(--color-border)" : "none",
              }}>
                {index < currentStep ? "✓" : index + 1}
              </div>
              <span style={{
                fontSize: 13,
                fontWeight: index === currentStep ? 600 : 400,
                color: index <= currentStep ? "var(--color-text)" : "var(--color-text-secondary)",
              }}>
                {step.title}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div style={{
                width: 32,
                height: 1,
                background: index < currentStep ? "var(--color-success)" : "var(--color-border)",
              }} />
            )}
          </React.Fragment>
        ))}
      </div>

      <div style={{
        flex: 1,
        overflow: "auto",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 32,
      }}>
        <div style={{ width: "100%", maxWidth: 560 }}>
          {children}
        </div>
      </div>
    </div>
  );
}
