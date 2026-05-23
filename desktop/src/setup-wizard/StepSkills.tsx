import React from "react";
import type { WizardConfig } from "./SetupWizard";

interface StepSkillsProps {
  config: WizardConfig;
  onUpdate: (partial: Partial<WizardConfig>) => void;
  onNext: () => void;
  onBack: () => void;
}

const AVAILABLE_SKILLS = [
  { id: "web-search", name: "Web Search", description: "Search the web for information using DuckDuckGo" },
  { id: "code-review", name: "Code Review", description: "Analyze and review code for quality and security" },
  { id: "file-manager", name: "File Manager", description: "Read, write, and manage files on your system" },
  { id: "data-analysis", name: "Data Analysis", description: "Analyze datasets and generate insights" },
  { id: "deep-research", name: "Deep Research", description: "Conduct in-depth research on topics" },
  { id: "consulting-analysis", name: "Consulting Analysis", description: "Strategic analysis and consulting reports" },
  { id: "chart-visualization", name: "Chart Visualization", description: "Generate charts and data visualizations" },
  { id: "image-generation", name: "Image Generation", description: "Generate images from text descriptions" },
];

export default function StepSkills({ config, onUpdate, onNext, onBack }: StepSkillsProps) {
  const toggleSkill = (skillId: string) => {
    const selected = config.selectedSkills.includes(skillId)
      ? config.selectedSkills.filter((id) => id !== skillId)
      : [...config.selectedSkills, skillId];
    onUpdate({ selectedSkills: selected });
  };

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 600, marginBottom: 8 }}>Select Skills</h2>
      <p style={{ color: "var(--color-text-secondary)", fontSize: 14, marginBottom: 24 }}>
        Choose which skills to enable. You can change this later.
      </p>

      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 12,
        marginBottom: 32,
      }}>
        {AVAILABLE_SKILLS.map((skill) => {
          const isSelected = config.selectedSkills.includes(skill.id);
          return (
            <label
              key={skill.id}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                padding: 14,
                background: isSelected ? "rgba(99, 102, 241, 0.1)" : "var(--color-surface)",
                border: `1px solid ${isSelected ? "var(--color-primary)" : "var(--color-border)"}`,
                borderRadius: "var(--radius)",
                cursor: "pointer",
                transition: "all 0.2s",
              }}
            >
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => toggleSkill(skill.id)}
                style={{ marginTop: 2 }}
              />
              <div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{skill.name}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-secondary)", marginTop: 2 }}>
                  {skill.description}
                </div>
              </div>
            </label>
          );
        })}
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
