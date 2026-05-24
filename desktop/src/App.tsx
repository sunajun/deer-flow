import React, { useState, useEffect } from "react";
import SetupWizard from "./setup-wizard/SetupWizard";
import MainView from "./MainView";
import ConsolePanel from "./console/ConsolePanel";
import SettingsPage from "./settings/SettingsPage";

const SETUP_COMPLETE_KEY = "deerflow-setup-complete";
const SETUP_STEP_KEY = "deerflow-setup-step";

export default function App() {
  const [setupComplete, setSetupComplete] = useState<boolean>(() => {
    return localStorage.getItem(SETUP_COMPLETE_KEY) === "true";
  });
  const [backendStatus, setBackendStatus] = useState<string>("starting");
  const [sandboxState, setSandboxState] = useState<string>("stopped");
  const [sandboxType, setSandboxType] = useState<string>("local");
  const [consoleVisible, setConsoleVisible] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    if (window.deerflow) {
      const unsubs: (() => void)[] = [];

      unsubs.push(
        window.deerflow.onBackendStatus((status) => {
          setBackendStatus(status);
        })
      );

      if (window.deerflow.onVMState) {
        unsubs.push(
          window.deerflow.onVMState((state) => {
            setSandboxState(state);
          })
        );
      }

      if (window.deerflow.detectSandbox) {
        window.deerflow.detectSandbox().then((info) => {
          if (info) {
            setSandboxType(info.type || "local");
          }
        });
      }

      return () => {
        unsubs.forEach((unsub) => unsub());
      };
    }
  }, []);

  const handleSetupComplete = () => {
    localStorage.setItem(SETUP_COMPLETE_KEY, "true");
    localStorage.removeItem(SETUP_STEP_KEY);
    setSetupComplete(true);
  };

  const toggleConsole = () => setConsoleVisible((v) => !v);
  const toggleSettings = () => setSettingsOpen((v) => !v);

  if (!setupComplete) {
    return <SetupWizard onComplete={handleSetupComplete} />;
  }

  if (settingsOpen) {
    return <SettingsPage onBack={() => setSettingsOpen(false)} />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, overflow: "hidden" }}>
        <MainView
          backendStatus={backendStatus}
          sandboxState={sandboxState}
          sandboxType={sandboxType}
          consoleVisible={consoleVisible}
          onToggleConsole={toggleConsole}
          onOpenSettings={toggleSettings}
        />
      </div>
      <ConsolePanel
        visible={consoleVisible}
        onToggle={toggleConsole}
        sandboxState={sandboxState}
        sandboxType={sandboxType}
      />
    </div>
  );
}
