import React, { useState, useEffect } from "react";
import WizardLayout from "./WizardLayout";
import StepWelcome from "./StepWelcome";
import StepSandbox from "./StepSandbox";
import StepApiKey from "./StepApiKey";
import StepSkills from "./StepSkills";
import StepReady from "./StepReady";

const SETUP_STEP_KEY = "deerflow-setup-step";

export interface WizardConfig {
  sandboxMode: "STRICT" | "SELECTIVE" | "LOCAL";
  sandboxType: string;
  sandboxAvailable: boolean;
  apiKeys: Record<string, string>;
  selectedSkills: string[];
}

const DEFAULT_CONFIG: WizardConfig = {
  sandboxMode: "SELECTIVE",
  sandboxType: "",
  sandboxAvailable: false,
  apiKeys: {},
  selectedSkills: ["web-search", "code-review", "file-manager"],
};

interface SetupWizardProps {
  onComplete: () => void;
}

const STEPS = [
  { id: "welcome", title: "Welcome" },
  { id: "sandbox", title: "Sandbox" },
  { id: "apikey", title: "API Keys" },
  { id: "skills", title: "Skills" },
  { id: "ready", title: "Ready" },
];

export default function SetupWizard({ onComplete }: SetupWizardProps) {
  const [currentStep, setCurrentStep] = useState<number>(() => {
    const saved = localStorage.getItem(SETUP_STEP_KEY);
    return saved ? parseInt(saved, 10) : 0;
  });
  const [config, setConfig] = useState<WizardConfig>(() => {
    const saved = localStorage.getItem("deerflow-setup-config");
    if (saved) {
      try { return { ...DEFAULT_CONFIG, ...JSON.parse(saved) }; } catch { /* ignore */ }
    }
    return DEFAULT_CONFIG;
  });

  useEffect(() => {
    localStorage.setItem(SETUP_STEP_KEY, String(currentStep));
  }, [currentStep]);

  useEffect(() => {
    localStorage.setItem("deerflow-setup-config", JSON.stringify(config));
  }, [config]);

  const handleNext = () => {
    if (currentStep < STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const updateConfig = (partial: Partial<WizardConfig>) => {
    setConfig((prev) => ({ ...prev, ...partial }));
  };

  const renderStep = () => {
    switch (currentStep) {
      case 0:
        return <StepWelcome onNext={handleNext} />;
      case 1:
        return <StepSandbox config={config} onUpdate={updateConfig} onNext={handleNext} onBack={handleBack} />;
      case 2:
        return <StepApiKey config={config} onUpdate={updateConfig} onNext={handleNext} onBack={handleBack} />;
      case 3:
        return <StepSkills config={config} onUpdate={updateConfig} onNext={handleNext} onBack={handleBack} />;
      case 4:
        return <StepReady config={config} onComplete={onComplete} onBack={handleBack} />;
      default:
        return null;
    }
  };

  return (
    <WizardLayout currentStep={currentStep} steps={STEPS}>
      {renderStep()}
    </WizardLayout>
  );
}
