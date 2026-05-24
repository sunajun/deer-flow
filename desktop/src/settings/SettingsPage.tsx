import React, { useState, useEffect } from "react";

type SettingsSection = "general" | "sandbox" | "api" | "updates" | "about";

interface Settings {
  autoStartBackend: boolean;
  closeBehavior: "minimize" | "quit";
  logLevel: "debug" | "info" | "warn" | "error";
  dataDirectory: string;
  sandboxPolicy: "STRICT" | "SELECTIVE" | "LOCAL";
  vmMemoryMB: number;
  vmCpuCount: number;
  vmWorkspacePath: string;
  autoDegradation: boolean;
  llmProvider: string;
  apiKey: string;
  proxyUrl: string;
  autoCheckUpdates: boolean;
  updateChannel: "stable" | "beta";
}

const DEFAULT_SETTINGS: Settings = {
  autoStartBackend: true,
  closeBehavior: "minimize",
  logLevel: "info",
  dataDirectory: "",
  sandboxPolicy: "SELECTIVE",
  vmMemoryMB: 2048,
  vmCpuCount: 2,
  vmWorkspacePath: "",
  autoDegradation: true,
  llmProvider: "openai",
  apiKey: "",
  proxyUrl: "",
  autoCheckUpdates: true,
  updateChannel: "stable",
};

const STORAGE_KEY = "deerflow-settings";

function loadSettings(): Settings {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) };
    }
  } catch {
    // ignore
  }
  return DEFAULT_SETTINGS;
}

function saveSettings(settings: Settings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

interface SettingsPageProps {
  onBack: () => void;
}

const sections: { key: SettingsSection; label: string }[] = [
  { key: "general", label: "通用" },
  { key: "sandbox", label: "沙箱" },
  { key: "api", label: "API" },
  { key: "updates", label: "更新" },
  { key: "about", label: "关于" },
];

export default function SettingsPage({ onBack }: SettingsPageProps) {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const [activeSection, setActiveSection] = useState<SettingsSection>("general");
  const [appVersion, setAppVersion] = useState("");

  useEffect(() => {
    if (window.deerflow?.getAppVersion) {
      window.deerflow.getAppVersion().then(setAppVersion);
    }
  }, []);

  const updateSetting = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    const next = { ...settings, [key]: value };
    setSettings(next);
    saveSettings(next);
  };

  return (
    <div style={{ display: "flex", height: "100%", background: "var(--color-bg)" }}>
      <div
        style={{
          width: 200,
          borderRight: "1px solid var(--color-border)",
          padding: "16px 0",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 16px 16px",
            borderBottom: "1px solid var(--color-border)",
            marginBottom: 8,
          }}
        >
          <button
            onClick={onBack}
            style={{
              background: "none",
              border: "none",
              color: "var(--color-text-secondary)",
              cursor: "pointer",
              fontSize: 16,
              padding: 0,
            }}
          >
            ←
          </button>
          <span style={{ fontWeight: 600, fontSize: 14 }}>偏好设置</span>
        </div>
        {sections.map((s) => (
          <button
            key={s.key}
            onClick={() => setActiveSection(s.key)}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              background: activeSection === s.key ? "var(--color-surface-hover)" : "none",
              border: "none",
              borderLeft: activeSection === s.key ? "2px solid var(--color-primary)" : "2px solid transparent",
              color: activeSection === s.key ? "var(--color-text)" : "var(--color-text-secondary)",
              padding: "8px 16px",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, padding: 24, overflowY: "auto" }}>
        {activeSection === "general" && (
          <div style={sectionStyle}>
            <h3 style={headingStyle}>通用设置</h3>
            <SettingToggle
              label="启动时自动启动后端"
              value={settings.autoStartBackend}
              onChange={(v) => updateSetting("autoStartBackend", v)}
            />
            <SettingSelect
              label="关闭窗口时行为"
              value={settings.closeBehavior}
              options={[
                { value: "minimize", label: "最小化到托盘" },
                { value: "quit", label: "退出应用" },
              ]}
              onChange={(v) => updateSetting("closeBehavior", v as Settings["closeBehavior"])}
            />
            <SettingSelect
              label="日志级别"
              value={settings.logLevel}
              options={[
                { value: "debug", label: "Debug" },
                { value: "info", label: "Info" },
                { value: "warn", label: "Warn" },
                { value: "error", label: "Error" },
              ]}
              onChange={(v) => updateSetting("logLevel", v as Settings["logLevel"])}
            />
            <SettingInput
              label="数据目录"
              value={settings.dataDirectory}
              placeholder="默认: ~/DeerFlow"
              onChange={(v) => updateSetting("dataDirectory", v)}
            />
          </div>
        )}

        {activeSection === "sandbox" && (
          <div style={sectionStyle}>
            <h3 style={headingStyle}>沙箱设置</h3>
            <SettingSelect
              label="沙箱策略"
              value={settings.sandboxPolicy}
              options={[
                { value: "STRICT", label: "严格模式 - 所有代码在沙箱中执行" },
                { value: "SELECTIVE", label: "选择模式 - 仅高风险代码在沙箱中执行" },
                { value: "LOCAL", label: "本地模式 - 直接在本地执行" },
              ]}
              onChange={(v) => updateSetting("sandboxPolicy", v as Settings["sandboxPolicy"])}
            />
            <SettingInput
              label="VM 内存 (MB)"
              value={String(settings.vmMemoryMB)}
              placeholder="2048"
              onChange={(v) => updateSetting("vmMemoryMB", parseInt(v) || 2048)}
            />
            <SettingInput
              label="VM CPU 核心数"
              value={String(settings.vmCpuCount)}
              placeholder="2"
              onChange={(v) => updateSetting("vmCpuCount", parseInt(v) || 2)}
            />
            <SettingInput
              label="工作目录路径"
              value={settings.vmWorkspacePath}
              placeholder="默认: 用户目录"
              onChange={(v) => updateSetting("vmWorkspacePath", v)}
            />
            <SettingToggle
              label="自动降级（沙箱不可用时切换到本地模式）"
              value={settings.autoDegradation}
              onChange={(v) => updateSetting("autoDegradation", v)}
            />
          </div>
        )}

        {activeSection === "api" && (
          <div style={sectionStyle}>
            <h3 style={headingStyle}>API 设置</h3>
            <SettingSelect
              label="LLM Provider"
              value={settings.llmProvider}
              options={[
                { value: "openai", label: "OpenAI" },
                { value: "anthropic", label: "Anthropic" },
                { value: "azure", label: "Azure OpenAI" },
                { value: "custom", label: "自定义" },
              ]}
              onChange={(v) => updateSetting("llmProvider", v)}
            />
            <SettingInput
              label="API Key"
              value={settings.apiKey}
              placeholder="sk-..."
              type="password"
              onChange={(v) => updateSetting("apiKey", v)}
            />
            <SettingInput
              label="代理地址"
              value={settings.proxyUrl}
              placeholder="http://127.0.0.1:7890"
              onChange={(v) => updateSetting("proxyUrl", v)}
            />
          </div>
        )}

        {activeSection === "updates" && (
          <div style={sectionStyle}>
            <h3 style={headingStyle}>更新设置</h3>
            <SettingToggle
              label="自动检查更新"
              value={settings.autoCheckUpdates}
              onChange={(v) => updateSetting("autoCheckUpdates", v)}
            />
            <SettingSelect
              label="更新频道"
              value={settings.updateChannel}
              options={[
                { value: "stable", label: "稳定版 (Stable)" },
                { value: "beta", label: "测试版 (Beta)" },
              ]}
              onChange={(v) => updateSetting("updateChannel", v as Settings["updateChannel"])}
            />
            <button
              onClick={() => window.deerflow?.checkForUpdates?.()}
              style={{
                marginTop: 12,
                padding: "8px 20px",
                background: "var(--color-primary)",
                color: "#fff",
                border: "none",
                borderRadius: "var(--radius)",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              立即检查更新
            </button>
          </div>
        )}

        {activeSection === "about" && (
          <div style={sectionStyle}>
            <h3 style={headingStyle}>关于 DeerFlow</h3>
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>DeerFlow</div>
              <div style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
                版本 {appVersion || "0.1.0"}
              </div>
            </div>
            <div style={{ color: "var(--color-text-secondary)", fontSize: 13, lineHeight: 1.8 }}>
              <p>DeerFlow 是一个带有轻量 VM 沙箱的 AI Agent 平台。</p>
              <p>支持 macOS Virtualization Framework、WSL2 和 Firecracker 沙箱。</p>
            </div>
            <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
              <a
                href="https://github.com/deerflow/deerflow"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--color-primary)", fontSize: 13, textDecoration: "none" }}
              >
                GitHub
              </a>
              <a
                href="https://github.com/deerflow/deerflow/issues"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--color-primary)", fontSize: 13, textDecoration: "none" }}
              >
                反馈
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const sectionStyle: React.CSSProperties = { maxWidth: 600 };
const headingStyle: React.CSSProperties = { fontSize: 16, fontWeight: 600, marginBottom: 16 };

function SettingToggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--color-border)" }}>
      <span style={{ fontSize: 13 }}>{label}</span>
      <button
        onClick={() => onChange(!value)}
        style={{
          width: 40,
          height: 22,
          borderRadius: 11,
          border: "none",
          background: value ? "var(--color-primary)" : "var(--color-border)",
          cursor: "pointer",
          position: "relative",
          transition: "background 0.2s",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 2,
            left: value ? 20 : 2,
            width: 18,
            height: 18,
            borderRadius: "50%",
            background: "#fff",
            transition: "left 0.2s",
          }}
        />
      </button>
    </div>
  );
}

function SettingSelect({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--color-border)" }}>
      <span style={{ fontSize: 13 }}>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: "var(--color-surface)",
          color: "var(--color-text)",
          border: "1px solid var(--color-border)",
          borderRadius: 4,
          padding: "4px 8px",
          fontSize: 13,
          outline: "none",
          minWidth: 160,
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function SettingInput({ label, value, placeholder, type = "text", onChange }: {
  label: string;
  value: string;
  placeholder?: string;
  type?: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid var(--color-border)" }}>
      <span style={{ fontSize: 13 }}>{label}</span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: "var(--color-surface)",
          color: "var(--color-text)",
          border: "1px solid var(--color-border)",
          borderRadius: 4,
          padding: "4px 8px",
          fontSize: 13,
          outline: "none",
          minWidth: 160,
          maxWidth: 240,
        }}
      />
    </div>
  );
}
