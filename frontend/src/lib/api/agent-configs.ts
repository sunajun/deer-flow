import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export interface AgentConfigVersion {
  name: string;
  description: string;
  model: string | null;
  tool_groups: string[] | null;
  skills: string[] | null;
  version: string;
  allowed_scenes: string[];
  skill_whitelist: string[] | null;
  skill_blacklist: string[] | null;
  max_retries: number;
  temperature: number;
  system_prompt_suffix: string;
  created_at: string;
  updated_at: string;
}

export interface AgentConfigVersionSnapshot {
  agent_name: string;
  version: string;
  snapshot: AgentConfigVersion;
  created_at: string;
  change_summary: string;
}

export interface CreateAgentConfigRequest {
  name: string;
  description?: string;
  model?: string | null;
  tool_groups?: string[] | null;
  skills?: string[] | null;
  version?: string;
  allowed_scenes?: string[];
  skill_whitelist?: string[] | null;
  skill_blacklist?: string[] | null;
  max_retries?: number;
  temperature?: number;
  system_prompt_suffix?: string;
}

export interface UpdateAgentConfigRequest {
  description?: string | null;
  model?: string | null;
  tool_groups?: string[] | null;
  skills?: string[] | null;
  allowed_scenes?: string[] | null;
  skill_whitelist?: string[] | null;
  skill_blacklist?: string[] | null;
  max_retries?: number | null;
  temperature?: number | null;
  system_prompt_suffix?: string | null;
  change_summary?: string;
}

const BASE = () => `${getBackendBaseURL()}/api/agent-configs`;

export async function listAgentConfigs(): Promise<AgentConfigVersion[]> {
  const res = await fetch(BASE());
  if (!res.ok) throw new Error(`Failed to list agent configs: ${res.statusText}`);
  const data = (await res.json()) as { configs: AgentConfigVersion[] };
  return data.configs;
}

export async function getAgentConfig(
  agentName: string,
): Promise<AgentConfigVersion> {
  const res = await fetch(`${BASE()}/${encodeURIComponent(agentName)}`);
  if (!res.ok)
    throw new Error(`Agent config '${agentName}' not found`);
  return res.json() as Promise<AgentConfigVersion>;
}

export async function createAgentConfig(
  data: CreateAgentConfigRequest,
): Promise<AgentConfigVersion> {
  const res = await fetch(BASE(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to create agent config: ${res.statusText}`);
  }
  return res.json() as Promise<AgentConfigVersion>;
}

export async function updateAgentConfig(
  agentName: string,
  data: UpdateAgentConfigRequest,
): Promise<AgentConfigVersion> {
  const res = await fetch(`${BASE()}/${encodeURIComponent(agentName)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to update agent config: ${res.statusText}`);
  }
  return res.json() as Promise<AgentConfigVersion>;
}

export async function deleteAgentConfig(
  agentName: string,
): Promise<void> {
  const res = await fetch(`${BASE()}/${encodeURIComponent(agentName)}`, {
    method: "DELETE",
  });
  if (!res.ok)
    throw new Error(`Failed to delete agent config: ${res.statusText}`);
}

export async function getAgentConfigVersions(
  agentName: string,
): Promise<AgentConfigVersionSnapshot[]> {
  const res = await fetch(
    `${BASE()}/${encodeURIComponent(agentName)}/versions`,
  );
  if (!res.ok)
    throw new Error(`Failed to get version history: ${res.statusText}`);
  const data = (await res.json()) as { versions: AgentConfigVersionSnapshot[] };
  return data.versions;
}

export async function rollbackAgentConfig(
  agentName: string,
  targetVersion: string,
): Promise<AgentConfigVersion> {
  const res = await fetch(
    `${BASE()}/${encodeURIComponent(agentName)}/rollback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version: targetVersion }),
    },
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to rollback agent config: ${res.statusText}`);
  }
  return res.json() as Promise<AgentConfigVersion>;
}
