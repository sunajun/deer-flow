import React, { useState, useEffect } from "react";
import SetupWizard from "./setup-wizard/SetupWizard";
import MainView from "./MainView";

const SETUP_COMPLETE_KEY = "deerflow-setup-complete";
const SETUP_STEP_KEY = "deerflow-setup-step";

export default function App() {
  const [setupComplete, setSetupComplete] = useState<boolean>(() => {
    return localStorage.getItem(SETUP_COMPLETE_KEY) === "true";
  });
  const [backendStatus, setBackendStatus] = useState<string>("starting");

  useEffect(() => {
    if (window.deerflow) {
      const unsub = window.deerflow.onBackendStatus((status) => {
        setBackendStatus(status);
      });
      return unsub;
    }
  }, []);

  const handleSetupComplete = () => {
    localStorage.setItem(SETUP_COMPLETE_KEY, "true");
    localStorage.removeItem(SETUP_STEP_KEY);
    setSetupComplete(true);
  };

  if (!setupComplete) {
    return <SetupWizard onComplete={handleSetupComplete} />;
  }

  return <MainView backendStatus={backendStatus} />;
}
